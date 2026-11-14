"""Locust load test for an existing Sentinel tenant and protected policy.

PowerShell:
  $env:SENTINEL_TEST_API_KEY = "<issued API key>"
  locust -f locustfile.py --host http://localhost:8000
"""
import os

from locust import HttpUser, between, task


class SentinelUser(HttpUser):
    wait_time = between(0.0, 0.05)

    def on_start(self):
        key = os.getenv("SENTINEL_TEST_API_KEY")
        if not key:
            raise RuntimeError("Set SENTINEL_TEST_API_KEY to an issued tenant API key")
        self.client.headers.update({"Authorization": f"Bearer {key}"})

    @task(10)
    def protected_ping(self):
        with self.client.get(
            "/api/v1/protected/ping",
            name="/api/v1/protected/ping",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 429):
                response.success()
            elif response.status_code == 503:
                response.failure("Sentinel rate-limit dependency unavailable")
            else:
                response.failure(f"Unexpected HTTP {response.status_code}")
