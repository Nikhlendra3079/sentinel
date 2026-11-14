from collections import defaultdict
import threading


HTTP_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)


class RateLimitMetrics:
    """Dependency-free Prometheus text collector with bounded label cardinality.

    Never label metrics with tenant IDs, API keys, policy IDs, or raw paths.
    These counters and histograms are process-local. A multi-worker deployment
    needs a multiprocess collector or an external aggregation strategy.
    """

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = defaultdict(int)
        self._http_counts: dict[tuple[str, str], int] = defaultdict(int)
        self._duration_buckets: dict[tuple[str, str], list[int]] = defaultdict(
            lambda: [0] * (len(HTTP_DURATION_BUCKETS) + 1)
        )
        self._duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._duration_count: dict[tuple[str, str], int] = defaultdict(int)
        self._lock = threading.Lock()

    def increment(self, algorithm: str, outcome: str) -> None:
        with self._lock:
            self._counts[(algorithm, outcome)] += 1

    def observe_http_request(self, duration_seconds: float, method: str, status_code: int) -> None:
        """Record request duration and count using bounded labels."""
        method_label = method.upper() if method.upper() in {
            "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"
        } else "OTHER"
        status_class = f"{int(status_code) // 100}xx"
        key = (method_label, status_class)
        duration = max(0.0, float(duration_seconds))
        with self._lock:
            self._http_counts[key] += 1
            self._duration_sum[key] += duration
            self._duration_count[key] += 1
            for index, boundary in enumerate(HTTP_DURATION_BUCKETS):
                if duration <= boundary:
                    self._duration_buckets[key][index] += 1
            self._duration_buckets[key][-1] += 1

    def render(self) -> str:
        with self._lock:
            snapshot = dict(self._counts)
            http_counts = dict(self._http_counts)
            buckets = {key: list(value) for key, value in self._duration_buckets.items()}
            sums = dict(self._duration_sum)
            totals = dict(self._duration_count)

        lines = [
            "# HELP sentinel_rate_limit_requests_total Rate-limit decisions by algorithm and outcome.",
            "# TYPE sentinel_rate_limit_requests_total counter",
        ]
        for (algorithm, outcome), value in sorted(snapshot.items()):
            lines.append(
                f'sentinel_rate_limit_requests_total{{algorithm="{algorithm}",'
                f'outcome="{outcome}"}} {value}'
            )

        lines.extend([
            "# HELP sentinel_http_requests_total HTTP requests by method and status class.",
            "# TYPE sentinel_http_requests_total counter",
        ])
        for (method, status_class), value in sorted(http_counts.items()):
            lines.append(
                f'sentinel_http_requests_total{{method="{method}",'
                f'status_class="{status_class}"}} {value}'
            )

        lines.extend([
            "# HELP sentinel_http_request_duration_seconds HTTP request duration in seconds.",
            "# TYPE sentinel_http_request_duration_seconds histogram",
        ])
        for key in sorted(totals):
            method, status_class = key
            labels = f'method="{method}",status_class="{status_class}"'
            for index, boundary in enumerate(HTTP_DURATION_BUCKETS):
                lines.append(
                    f'sentinel_http_request_duration_seconds_bucket{{{labels},'
                    f'le="{boundary:g}"}} {buckets[key][index]}'
                )
            lines.append(
                f'sentinel_http_request_duration_seconds_bucket{{{labels},le="+Inf"}} '
                f'{buckets[key][-1]}'
            )
            lines.append(
                f'sentinel_http_request_duration_seconds_sum{{{labels}}} {sums[key]:.9f}'
            )
            lines.append(
                f'sentinel_http_request_duration_seconds_count{{{labels}}} {totals[key]}'
            )
        return "\n".join(lines) + "\n"
