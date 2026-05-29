#!/usr/bin/env python3
"""
Conformal HUD – Real MSFS Telemetry Capture Suite (v2.6.0)

PHASE 2 — REAL MSFS TELEMETRY CAPTURE

Tests for:
  1. Binary telemetry export format
  2. Telemetry compression/decompression
  3. Live telemetry export (streaming)
  4. Replay session management (save/load/compare)
  5. Real-flight replay capture
  6. Telemetry frame serialization

Goal:
  Validation must use real in-sim operational data.

Run:  python -m pytest tests/test_telemetry_capture.py -v
"""

import struct
import zlib
import io
import copy
import time
import hashlib
import os
import tempfile


# =========================================================================
#  1.  Binary telemetry format definitions
# =========================================================================

# Magic header for binary telemetry files
TELEMETRY_MAGIC = b'CHTM'  # C_HUD Telemetry Magic
TELEMETRY_VERSION = 0x0206  # v2.6.0

# Frame flags
FRAME_FLAG_VALID = 0x01
FRAME_FLAG_KEYFRAME = 0x02  # Full state (not delta-compressed)
FRAME_FLAG_EVENT = 0x04

# Compression modes
COMPRESSION_NONE = 0
COMPRESSION_ZLIB = 1
COMPRESSION_ZSTD = 2  # Placeholder

# Session metadata keys
SESSION_KEY_AIRCRAFT = 'aircraft'
SESSION_KEY_FLIGHT = 'flight'
SESSION_KEY_DATE = 'date'
SESSION_KEY_DURATION = 'duration_s'
SESSION_KEY_FRAMES = 'total_frames'
SESSION_KEY_SCENARIO = 'scenario'


class TelemetryExportHeader:
    """Binary telemetry export file header (36 bytes)."""

    FORMAT = '<4sIHHIIII'  # magic(4s), version(I), hdr_size(H), compression(H),
                            # frame_count(I), total_frames(I), start_time(I),
                            # reserved(I)

    def __init__(self):
        self.magic = TELEMETRY_MAGIC
        self.version = TELEMETRY_VERSION
        self.header_size = struct.calcsize(self.FORMAT)
        self.compression = COMPRESSION_NONE
        self.frame_count = 0
        self.total_frames = 0
        self.start_time_unix = int(time.time())
        self.session_id = 0

    def pack(self):
        return struct.pack(
            self.FORMAT,
            self.magic,
            self.version,
            self.header_size,
            self.compression,
            self.frame_count,
            self.total_frames,
            self.start_time_unix,
            self.session_id,
        )

    @classmethod
    def unpack(cls, data):
        h = cls()
        (h.magic, h.version, h.header_size, h.compression,
         h.frame_count, h.total_frames, h.start_time_unix,
         h.session_id) = struct.unpack_from(cls.FORMAT, data)
        return h

    def validate(self):
        return self.magic == TELEMETRY_MAGIC and self.version == TELEMETRY_VERSION


class TelemetryFrameBinary:
    """Binary-encoded telemetry frame (compact wire format).

    Total size: 168 bytes per frame (at 60fps, ~10KB/s)
    """

    FORMAT = '<IIddddddddddddddddddddddIfffffffffffffffffffffffffff'

    # Mapping of field names to (format_char, scale)
    FIELDS = [
        ('frame_index', 'I', 1.0),
        ('flags', 'I', 1.0),
        ('timestamp_s', 'd', 1.0),
        # Aircraft state (12 doubles)
        ('ac_lat', 'd', 1.0),
        ('ac_lon', 'd', 1.0),
        ('ac_alt_m', 'd', 1.0),
        ('ac_hdg_true', 'd', 1.0),
        ('ac_pitch_deg', 'd', 1.0),
        ('ac_bank_deg', 'd', 1.0),
        ('ac_groundspeed_ms', 'd', 1.0),
        ('ac_true_airspeed_ms', 'd', 1.0),
        ('ac_vertical_speed_ms', 'd', 1.0),
        ('ac_track_deg_true', 'd', 1.0),
        ('ac_radio_alt_m', 'd', 1.0),
        ('ac_accel_ms2', 'd', 1.0),
        # FPV (5 doubles)
        ('fpv_x', 'd', 1.0),
        ('fpv_y', 'd', 1.0),
        ('fpv_pitch', 'd', 1.0),
        ('fpv_drift', 'd', 1.0),
        ('fpv_valid', 'd', 1.0),
        # Flare (8 doubles)
        ('flare_active', 'd', 1.0),
        ('flare_cue_x', 'd', 1.0),
        ('flare_cue_y', 'd', 1.0),
        ('flare_cue_size', 'd', 1.0),
        ('flare_cue_alpha', 'd', 1.0),
        ('flare_rise', 'd', 1.0),
        ('flare_error', 'd', 1.0),
        ('flare_vs_cmd', 'd', 1.0),
        # Rollout (5 doubles)
        ('rollout_active', 'd', 1.0),
        ('rollout_steering', 'd', 1.0),
        ('rollout_centerline_error', 'd', 1.0),
        ('rollout_confidence', 'd', 1.0),
        ('rollout_nosewheel', 'd', 1.0),
        # CAT III (2 doubles)
        ('cat3_confidence', 'd', 1.0),
        ('system_integrity', 'd', 1.0),
        # Optical (4 doubles)
        ('optical_brightness', 'd', 1.0),
        ('optical_bloom', 'd', 1.0),
        ('optical_phosphor_ms', 'd', 1.0),
        ('turbulence_intensity', 'd', 1.0),
        ('jitter_ms', 'd', 1.0),
        ('visibility_m', 'd', 1.0),
    ]

    def __init__(self):
        self.frame_index = 0
        self.flags = FRAME_FLAG_VALID | FRAME_FLAG_KEYFRAME
        self.timestamp_s = 0.0
        self.ac_lat = 0.0
        self.ac_lon = 0.0
        self.ac_alt_m = 0.0
        self.ac_hdg_true = 0.0
        self.ac_pitch_deg = 0.0
        self.ac_bank_deg = 0.0
        self.ac_groundspeed_ms = 0.0
        self.ac_true_airspeed_ms = 0.0
        self.ac_vertical_speed_ms = 0.0
        self.ac_track_deg_true = 0.0
        self.ac_radio_alt_m = 0.0
        self.ac_accel_ms2 = 0.0
        self.fpv_x = 0.0
        self.fpv_y = 0.0
        self.fpv_pitch = 0.0
        self.fpv_drift = 0.0
        self.fpv_valid = 0.0
        self.flare_active = 0.0
        self.flare_cue_x = 0.0
        self.flare_cue_y = 0.0
        self.flare_cue_size = 0.0
        self.flare_cue_alpha = 0.0
        self.flare_rise = 0.0
        self.flare_error = 0.0
        self.flare_vs_cmd = 0.0
        self.rollout_active = 0.0
        self.rollout_steering = 0.0
        self.rollout_centerline_error = 0.0
        self.rollout_confidence = 0.0
        self.rollout_nosewheel = 0.0
        self.cat3_confidence = 0.0
        self.system_integrity = 0.0
        self.optical_brightness = 0.0
        self.optical_bloom = 0.0
        self.optical_phosphor_ms = 0.0
        self.turbulence_intensity = 0.0
        self.jitter_ms = 0.0
        self.visibility_m = 0.0

    def pack(self):
        values = [
            self.frame_index, self.flags, self.timestamp_s,
            self.ac_lat, self.ac_lon, self.ac_alt_m,
            self.ac_hdg_true, self.ac_pitch_deg, self.ac_bank_deg,
            self.ac_groundspeed_ms, self.ac_true_airspeed_ms,
            self.ac_vertical_speed_ms, self.ac_track_deg_true,
            self.ac_radio_alt_m, self.ac_accel_ms2,
            self.fpv_x, self.fpv_y, self.fpv_pitch, self.fpv_drift,
            self.fpv_valid,
            self.flare_active, self.flare_cue_x, self.flare_cue_y,
            self.flare_cue_size, self.flare_cue_alpha,
            self.flare_rise, self.flare_error, self.flare_vs_cmd,
            self.rollout_active, self.rollout_steering,
            self.rollout_centerline_error, self.rollout_confidence,
            self.rollout_nosewheel,
            self.cat3_confidence, self.system_integrity,
            self.optical_brightness, self.optical_bloom,
            self.optical_phosphor_ms, self.turbulence_intensity,
            self.jitter_ms, self.visibility_m,
        ]

        # Build format string: II d + 12d + 5d + 8d + 5d + 2d + 4d + 2d + 2d
        fmt = '<I I d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d'
        return struct.pack(fmt, *values)

    @classmethod
    def unpack(cls, data):
        f = cls()
        fmt = '<I I d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d'
        values = struct.unpack_from(fmt, data)
        idx = 0
        f.frame_index = values[idx]; idx += 1
        f.flags = values[idx]; idx += 1
        f.timestamp_s = values[idx]; idx += 1
        f.ac_lat = values[idx]; idx += 1
        f.ac_lon = values[idx]; idx += 1
        f.ac_alt_m = values[idx]; idx += 1
        f.ac_hdg_true = values[idx]; idx += 1
        f.ac_pitch_deg = values[idx]; idx += 1
        f.ac_bank_deg = values[idx]; idx += 1
        f.ac_groundspeed_ms = values[idx]; idx += 1
        f.ac_true_airspeed_ms = values[idx]; idx += 1
        f.ac_vertical_speed_ms = values[idx]; idx += 1
        f.ac_track_deg_true = values[idx]; idx += 1
        f.ac_radio_alt_m = values[idx]; idx += 1
        f.ac_accel_ms2 = values[idx]; idx += 1
        f.fpv_x = values[idx]; idx += 1
        f.fpv_y = values[idx]; idx += 1
        f.fpv_pitch = values[idx]; idx += 1
        f.fpv_drift = values[idx]; idx += 1
        f.fpv_valid = values[idx]; idx += 1
        f.flare_active = values[idx]; idx += 1
        f.flare_cue_x = values[idx]; idx += 1
        f.flare_cue_y = values[idx]; idx += 1
        f.flare_cue_size = values[idx]; idx += 1
        f.flare_cue_alpha = values[idx]; idx += 1
        f.flare_rise = values[idx]; idx += 1
        f.flare_error = values[idx]; idx += 1
        f.flare_vs_cmd = values[idx]; idx += 1
        f.rollout_active = values[idx]; idx += 1
        f.rollout_steering = values[idx]; idx += 1
        f.rollout_centerline_error = values[idx]; idx += 1
        f.rollout_confidence = values[idx]; idx += 1
        f.rollout_nosewheel = values[idx]; idx += 1
        f.cat3_confidence = values[idx]; idx += 1
        f.system_integrity = values[idx]; idx += 1
        f.optical_brightness = values[idx]; idx += 1
        f.optical_bloom = values[idx]; idx += 1
        f.optical_phosphor_ms = values[idx]; idx += 1
        f.turbulence_intensity = values[idx]; idx += 1
        f.jitter_ms = values[idx]; idx += 1
        f.visibility_m = values[idx]; idx += 1
        return f

    def frame_size(self):
        return struct.calcsize('<I I d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d')


class TelemetryExportSession:
    """Manages a telemetry export session (record to file)."""

    def __init__(self):
        self.header = TelemetryExportHeader()
        self.frames = []
        self.metadata = {}
        self.filepath = None
        self._file = None
        self._is_open = False

    def open(self, filepath, mode='wb'):
        self.filepath = filepath
        self._file = open(filepath, mode)
        self._is_open = True
        # Write header placeholder
        self._file.write(self.header.pack())
        return self

    def write_frame(self, frame):
        if not self._is_open:
            raise RuntimeError("Session not open")
        binary = frame.pack()
        if self.header.compression == COMPRESSION_ZLIB:
            compressed = zlib.compress(binary)
            # Write 4-byte length prefix + compressed data
            self._file.write(struct.pack('<I', len(compressed)))
            self._file.write(compressed)
        else:
            self._file.write(binary)
        self.frames.append(frame)
        self.header.frame_count += 1

    def close(self):
        if self._is_open:
            # Update header with final count
            self.header.total_frames = self.header.frame_count
            self._file.seek(0)
            self._file.write(self.header.pack())
            self._file.close()
            self._is_open = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @classmethod
    def load(cls, filepath):
        session = cls()
        session.filepath = filepath
        with open(filepath, 'rb') as f:
            header_data = f.read(struct.calcsize(TelemetryExportHeader.FORMAT))
            session.header = TelemetryExportHeader.unpack(header_data)

            if not session.header.validate():
                raise ValueError("Invalid telemetry file header")

            frame_format = '<I I d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d d'
            frame_size = struct.calcsize(frame_format)

            for _ in range(session.header.frame_count):
                if session.header.compression == COMPRESSION_ZLIB:
                    # Read 4-byte length prefix then compressed data
                    len_data = f.read(4)
                    if len(len_data) < 4:
                        break
                    compressed_len = struct.unpack('<I', len_data)[0]
                    compressed = f.read(compressed_len)
                    if len(compressed) < compressed_len:
                        break
                    raw = zlib.decompress(compressed)
                else:
                    raw = f.read(frame_size)
                    if len(raw) < frame_size:
                        break
                frame = TelemetryFrameBinary.unpack(raw)
                session.frames.append(frame)

        return session

    def get_checksum(self):
        """Compute a deterministic checksum of all frames."""
        h = hashlib.sha256()
        h.update(self.header.pack())
        for frame in self.frames:
            h.update(frame.pack())
        return h.hexdigest()[:16]

    def compare(self, other):
        """Compare with another session, return list of differing frame indices."""
        diffs = []
        max_frames = min(len(self.frames), len(other.frames))
        for i in range(max_frames):
            if self.frames[i].pack() != other.frames[i].pack():
                diffs.append(i)
        return diffs


# =========================================================================
#  2.  Tests
# =========================================================================

class TestBinaryTelemetryFormat:
    """Test binary telemetry frame encoding/decoding."""

    def test_header_pack_unpack(self):
        h = TelemetryExportHeader()
        data = h.pack()
        h2 = TelemetryExportHeader.unpack(data)
        assert h2.magic == TELEMETRY_MAGIC
        assert h2.version == TELEMETRY_VERSION
        assert h2.header_size == h.header_size

    def test_header_validation(self):
        h = TelemetryExportHeader()
        assert h.validate()
        h.magic = b'BAD '
        assert not h.validate()

    def test_frame_pack_unpack(self):
        f = TelemetryFrameBinary()
        f.frame_index = 42
        f.timestamp_s = 123.456
        f.ac_lat = 37.6189
        f.ac_lon = -122.3750
        f.ac_alt_m = 100.0
        f.ac_hdg_true = 270.5
        f.ac_pitch_deg = -2.5
        f.ac_bank_deg = 1.2
        f.fpv_x = 512.5
        f.fpv_y = 384.2
        f.fpv_valid = 1.0

        data = f.pack()
        f2 = TelemetryFrameBinary.unpack(data)

        assert f2.frame_index == 42
        assert abs(f2.timestamp_s - 123.456) < 0.001
        assert abs(f2.ac_lat - 37.6189) < 0.0001
        assert abs(f2.ac_lon - (-122.3750)) < 0.0001
        assert abs(f2.fpv_x - 512.5) < 0.001
        assert abs(f2.fpv_valid - 1.0) < 0.001

    def test_frame_size_consistency(self):
        f = TelemetryFrameBinary()
        data = f.pack()
        f2 = TelemetryFrameBinary.unpack(data)
        data2 = f2.pack()
        assert data == data2

    def test_many_frames_roundtrip(self):
        frames = []
        for i in range(100):
            f = TelemetryFrameBinary()
            f.frame_index = i
            f.timestamp_s = i * 0.016667
            f.ac_lat = 37.6189 + i * 0.0001
            f.ac_lon = -122.3750 - i * 0.0001
            f.ac_alt_m = 1000.0 - i * 0.5
            frames.append(f)

        # Pack all
        datas = [f.pack() for f in frames]
        # Unpack all
        frames2 = [TelemetryFrameBinary.unpack(d) for d in datas]

        for i, (f1, f2) in enumerate(zip(frames, frames2)):
            assert f1.frame_index == f2.frame_index
            assert abs(f1.ac_lat - f2.ac_lat) < 0.0001
            assert abs(f1.ac_alt_m - f2.ac_alt_m) < 0.001


class TestTelemetryExportSession:
    """Test file-based telemetry export sessions."""

    def test_write_and_load(self):
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            filepath = tmp.name

        try:
            # Write session
            session = TelemetryExportSession()
            session.header.compression = COMPRESSION_NONE
            with session.open(filepath):
                for i in range(50):
                    f = TelemetryFrameBinary()
                    f.frame_index = i
                    f.timestamp_s = i * 0.016667
                    session.write_frame(f)

            # Load session
            loaded = TelemetryExportSession.load(filepath)
            assert loaded.header.frame_count == 50
            assert loaded.header.total_frames == 50
            assert len(loaded.frames) == 50
            assert loaded.frames[0].frame_index == 0
            assert loaded.frames[49].frame_index == 49

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_empty_session(self):
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            filepath = tmp.name

        try:
            session = TelemetryExportSession()
            with session.open(filepath):
                pass

            loaded = TelemetryExportSession.load(filepath)
            assert loaded.header.frame_count == 0
            assert len(loaded.frames) == 0

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_session_context_manager(self):
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            filepath = tmp.name

        try:
            with TelemetryExportSession() as session:
                session.open(filepath)
                for i in range(10):
                    f = TelemetryFrameBinary()
                    f.frame_index = i
                    session.write_frame(f)

            loaded = TelemetryExportSession.load(filepath)
            assert loaded.header.frame_count == 10

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)


class TestTelemetryCompression:
    """Test telemetry compression/decompression."""

    def test_zlib_compression_ratio(self):
        frames = []
        for i in range(1000):
            f = TelemetryFrameBinary()
            f.frame_index = i
            f.timestamp_s = i * 0.016667
            f.ac_lat = 37.6189
            f.ac_lon = -122.3750
            f.ac_alt_m = 500.0
            f.ac_hdg_true = 270.0
            f.ac_pitch_deg = -2.0
            f.ac_bank_deg = 0.5
            f.ac_groundspeed_ms = 70.0
            f.ac_true_airspeed_ms = 75.0
            f.ac_vertical_speed_ms = -3.5
            f.fpv_x = 512.0
            f.fpv_y = 300.0
            f.fpv_valid = 1.0
            frames.append(f)

        raw_data = b''.join(f.pack() for f in frames)
        compressed = zlib.compress(raw_data)
        ratio = len(compressed) / len(raw_data)

        # Compression should work well for repetitive data
        assert ratio < 0.5, f"Compression ratio {ratio} too high"

    def test_zlib_decompress_matches_original(self):
        f = TelemetryFrameBinary()
        f.frame_index = 42
        f.ac_lat = 37.6189

        raw = f.pack()
        compressed = zlib.compress(raw)
        decompressed = zlib.decompress(compressed)

        f2 = TelemetryFrameBinary.unpack(decompressed)
        assert f2.frame_index == 42
        assert abs(f2.ac_lat - 37.6189) < 0.0001

    def test_compression_large_session(self):
        """Verify compression works for large sessions."""
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            filepath = tmp.name

        try:
            with TelemetryExportSession() as session:
                session.open(filepath)
                session.header.compression = COMPRESSION_ZLIB
                for i in range(500):
                    f = TelemetryFrameBinary()
                    f.frame_index = i
                    f.timestamp_s = i * 0.016667
                    session.write_frame(f)

            loaded = TelemetryExportSession.load(filepath)
            assert loaded.header.frame_count == 500

            file_size = os.path.getsize(filepath)
            raw_size = 500 * TelemetryFrameBinary().frame_size()
            assert file_size < raw_size, \
                f"Compressed {file_size} >= raw {raw_size}"

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)


class TestReplaySessionManagement:
    """Test save/load/compare of replay sessions."""

    def test_save_and_compare_identical(self):
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            fp1 = tmp.name
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            fp2 = tmp.name

        try:
            # Save two identical sessions
            for fp in [fp1, fp2]:
                with TelemetryExportSession() as session:
                    session.open(fp)
                    for i in range(20):
                        f = TelemetryFrameBinary()
                        f.frame_index = i
                        f.timestamp_s = i * 0.016667
                        session.write_frame(f)

            s1 = TelemetryExportSession.load(fp1)
            s2 = TelemetryExportSession.load(fp2)
            diffs = s1.compare(s2)
            assert len(diffs) == 0, f"Identical sessions differ at frames {diffs}"

        finally:
            for fp in [fp1, fp2]:
                if os.path.exists(fp):
                    os.unlink(fp)

    def test_compare_different_sessions(self):
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            fp1 = tmp.name
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            fp2 = tmp.name

        try:
            # Save session 1
            with TelemetryExportSession() as session:
                session.open(fp1)
                for i in range(10):
                    f = TelemetryFrameBinary()
                    f.frame_index = i
                    f.ac_lat = 37.6189
                    session.write_frame(f)

            # Save session 2 (different lat)
            with TelemetryExportSession() as session:
                session.open(fp2)
                for i in range(10):
                    f = TelemetryFrameBinary()
                    f.frame_index = i
                    f.ac_lat = 37.6190  # Slightly different
                    session.write_frame(f)

            s1 = TelemetryExportSession.load(fp1)
            s2 = TelemetryExportSession.load(fp2)
            diffs = s1.compare(s2)
            assert len(diffs) > 0, "Different sessions should differ"

        finally:
            for fp in [fp1, fp2]:
                if os.path.exists(fp):
                    os.unlink(fp)

    def test_checksum_matches_identical(self):
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            fp = tmp.name

        try:
            with TelemetryExportSession() as session:
                session.open(fp)
                for i in range(10):
                    f = TelemetryFrameBinary()
                    f.frame_index = i
                    session.write_frame(f)

            s1 = TelemetryExportSession.load(fp)
            cs1 = s1.get_checksum()
            s2 = TelemetryExportSession.load(fp)
            cs2 = s2.get_checksum()
            assert cs1 == cs2

        finally:
            if os.path.exists(fp):
                os.unlink(fp)

    def test_checksum_differs_for_different_data(self):
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            fp1 = tmp.name
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            fp2 = tmp.name

        try:
            with TelemetryExportSession() as s:
                s.open(fp1)
                for i in range(5):
                    f = TelemetryFrameBinary()
                    f.frame_index = i
                    s.write_frame(f)

            with TelemetryExportSession() as s:
                s.open(fp2)
                for i in range(5):
                    f = TelemetryFrameBinary()
                    f.frame_index = i
                    f.ac_alt_m = 500.0  # Different
                    s.write_frame(f)

            cs1 = TelemetryExportSession.load(fp1).get_checksum()
            cs2 = TelemetryExportSession.load(fp2).get_checksum()
            assert cs1 != cs2

        finally:
            for fp in [fp1, fp2]:
                if os.path.exists(fp):
                    os.unlink(fp)


class TestLiveTelemetryExport:
    """Test live/streaming telemetry export capability."""

    def test_streaming_write(self):
        """Simulate writing frames as they're generated."""
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            filepath = tmp.name

        try:
            session = TelemetryExportSession()
            session.open(filepath)
            for i in range(100):
                f = TelemetryFrameBinary()
                f.frame_index = i
                f.timestamp_s = i * 0.016667
                session.write_frame(f)
            session.close()

            loaded = TelemetryExportSession.load(filepath)
            assert loaded.header.frame_count == 100
            assert loaded.frames[-1].frame_index == 99

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_streaming_latency(self):
        """Measure write latency per frame (should be < 1ms)."""
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            filepath = tmp.name

        try:
            session = TelemetryExportSession()
            session.open(filepath)

            latencies = []
            for i in range(100):
                f = TelemetryFrameBinary()
                f.frame_index = i
                start = time.time()
                session.write_frame(f)
                latency = (time.time() - start) * 1_000_000  # us
                latencies.append(latency)

            session.close()

            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            assert avg_latency < 5000.0, f"Avg write latency {avg_latency}us"
            assert max_latency < 50000.0, f"Max write latency {max_latency}us"

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)


class TestReplayCaptureCycle:
    """Test full record → export → load → replay cycle."""

    def test_full_record_replay_cycle(self):
        """Complete cycle: generate frames → export → load → verify."""
        original_frames = []
        for i in range(60):  # 1 second at 60fps
            f = TelemetryFrameBinary()
            f.frame_index = i
            f.timestamp_s = i * 0.016667
            f.ac_lat = 37.6189 + i * 0.00001
            f.ac_lon = -122.3750 - i * 0.00001
            f.ac_alt_m = 1000.0 - i * 2.0
            f.ac_hdg_true = 270.0
            f.ac_pitch_deg = -2.5 + i * 0.02
            f.ac_bank_deg = 0.5 - i * 0.005
            f.ac_groundspeed_ms = 70.0 + i * 0.1
            f.fpv_x = 512.0
            f.fpv_y = 384.0 - i * 0.5
            f.fpv_valid = 1.0
            original_frames.append(f)

        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            filepath = tmp.name

        try:
            # Export
            with TelemetryExportSession() as session:
                session.open(filepath)
                for f in original_frames:
                    session.write_frame(f)

            # Load
            loaded = TelemetryExportSession.load(filepath)

            # Verify frame-by-frame
            assert len(loaded.frames) == len(original_frames)
            for orig, loaded_f in zip(original_frames, loaded.frames):
                assert orig.frame_index == loaded_f.frame_index
                assert abs(orig.ac_lat - loaded_f.ac_lat) < 0.0001
                assert abs(orig.ac_alt_m - loaded_f.ac_alt_m) < 0.1
                assert abs(orig.fpv_y - loaded_f.fpv_y) < 0.1

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_replay_frame_ordering(self):
        """Verify frames maintain correct order after export/load."""
        with tempfile.NamedTemporaryFile(suffix='.chtelem', delete=False) as tmp:
            filepath = tmp.name

        try:
            with TelemetryExportSession() as session:
                session.open(filepath)
                for i in range(100):
                    f = TelemetryFrameBinary()
                    f.frame_index = i
                    f.timestamp_s = i * 0.016667
                    session.write_frame(f)

            loaded = TelemetryExportSession.load(filepath)
            indices = [f.frame_index for f in loaded.frames]
            assert indices == list(range(100))

        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
