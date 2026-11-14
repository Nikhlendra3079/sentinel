from app.limiter.metrics import RateLimitMetrics


def test_metrics_aggregate_low_cardinality_algorithm_outcomes():
    metrics = RateLimitMetrics()
    metrics.increment("token_bucket", "allowed")
    metrics.increment("token_bucket", "allowed")
    metrics.increment("token_bucket", "denied")
    rendered = metrics.render()
    assert 'algorithm="token_bucket",outcome="allowed"} 2' in rendered
    assert 'algorithm="token_bucket",outcome="denied"} 1' in rendered


def test_http_histogram_has_bounded_labels_and_prometheus_buckets():
    metrics = RateLimitMetrics()
    metrics.observe_http_request(0.02, "GET", 200)
    metrics.observe_http_request(0.30, "SOME-UNBOUNDED-METHOD", 429)
    rendered = metrics.render()
    assert 'sentinel_http_requests_total{method="GET",status_class="2xx"} 1' in rendered
    assert 'sentinel_http_requests_total{method="OTHER",status_class="4xx"} 1' in rendered
    assert 'sentinel_http_request_duration_seconds_bucket' in rendered
    assert 'le="+Inf"' in rendered
    assert "SOME-UNBOUNDED-METHOD" not in rendered
