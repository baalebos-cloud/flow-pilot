from collections import Counter

from app.main import app


def test_no_duplicate_http_method_and_path_registrations():
    registrations = [
        (method, route.path)
        for route in app.routes
        if hasattr(route, "path")
        for method in getattr(route, "methods", set())
    ]
    duplicates = [item for item, count in Counter(registrations).items() if count > 1]

    assert duplicates == []


def test_transaction_signing_payload_route_is_registered_once():
    matches = [
        route
        for route in app.routes
        if getattr(route, "path", None)
        == "/v1/transactions/{transaction_id}/signing-payload"
        and "GET" in getattr(route, "methods", set())
    ]

    assert len(matches) == 1
