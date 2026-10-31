import unittest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, get_db

class TestTelemetryPipeline(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        self.client = TestClient(app)

    async def test_ingest_telemetry_with_audio_and_transport(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "device_id": "esp32-zone-a-01",
            "zone_id": "zone-a",
            "timestamp": now_iso,
            "co2_ppm": 1827.0,
            "temperature_c": 25.4,
            "relative_humidity_pct": 68.1,
            "co2_valid": True,
            "temp_valid": True,
            "rh_valid": True,
            "audio_rms": 142100.0,
            "audio_peak": 265000,
            "audio_rms_dbfs": -35.4,
            "audio_peak_dbfs": -30.0,
            "audio_valid": True,
            "transport": "usb_serial",
            "firmware_version": "2.0.0-PROTOTYPE",
            "source": "REAL",
        }

        resp = self.client.post("/api/telemetry", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["device_id"], "esp32-zone-a-01")
        self.assertEqual(data["co2_ppm"], 1827.0)
        self.assertEqual(data["relative_humidity_pct"], 68.1)
        self.assertEqual(data["audio_rms_dbfs"], -35.4)
        self.assertEqual(data["audio_peak_dbfs"], -30.0)
        self.assertEqual(data["transport"], "usb_serial")

    async def test_get_latest_telemetry_endpoint(self):
        # Post a fresh reading
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "device_id": "esp32-zone-a-01",
            "zone_id": "zone-a",
            "timestamp": now_iso,
            "co2_ppm": 1825.0,
            "temperature_c": 25.4,
            "relative_humidity_pct": 68.2,
            "audio_rms_dbfs": -36.0,
            "audio_peak_dbfs": -31.5,
            "transport": "usb_serial",
            "source": "REAL",
        }
        self.client.post("/api/telemetry", json=payload)

        resp = self.client.get("/api/telemetry/latest?device_id=esp32-zone-a-01")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("reading", data)
        self.assertTrue(data["is_hardware"])
        self.assertEqual(data["source"], "REAL")
        self.assertEqual(data["transport"], "usb_serial")
        self.assertIsNotNone(data["reading"]["audio_rms_dbfs"])

    async def test_get_telemetry_history_time_ranges(self):
        for tr in ["5m", "15m", "1h", "6h", "24h", "all"]:
            resp = self.client.get(f"/api/telemetry/history?time_range={tr}&device_id=esp32-zone-a-01")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("readings", data)
            self.assertGreater(data["count"], 0)
            self.assertEqual(data["time_range"], tr)

    async def test_device_inventory_updates_from_telemetry(self):
        resp = self.client.get("/api/devices")
        self.assertEqual(resp.status_code, 200)
        devices = resp.json()
        node_a = next((d for d in devices if d["id"] == "esp32-zone-a-01"), None)
        self.assertIsNotNone(node_a)
        self.assertTrue(node_a["connected"])
