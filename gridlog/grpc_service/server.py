"""gRPC surface over the GridLog query module."""

from concurrent import futures
from datetime import UTC, datetime

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from grpc_reflection.v1alpha import reflection

from gridlog.grpc_service.generated import prices_pb2, prices_pb2_grpc
from gridlog.query import get_latest_prices, get_price_revisions, get_prices_as_of

ALLOWED_ZONES = {"SE3"}


def _ts_to_dt(ts: Timestamp) -> datetime:
    return ts.ToDatetime(tzinfo=UTC)


def _dt_to_ts(dt: datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(dt.astimezone(UTC))
    return ts


def _require_zone(context: grpc.ServicerContext, zone: str) -> None:
    if zone not in ALLOWED_ZONES:
        context.abort(
            grpc.StatusCode.INVALID_ARGUMENT,
            f"unknown zone {zone!r}; allowed: {sorted(ALLOWED_ZONES)}",
        )


class PriceService(prices_pb2_grpc.PriceServiceServicer):
    def GetLatest(self, request, context):
        _require_zone(context, request.zone)
        df = get_latest_prices(
            request.zone, _ts_to_dt(request.start), _ts_to_dt(request.end)
        ).reset_index()
        return prices_pb2.PriceResponse(
            rows=[
                prices_pb2.PriceRow(valid_time=_dt_to_ts(row.valid_time), value=row.value)
                for row in df.itertuples(index=False)
            ]
        )

    def GetAsOf(self, request, context):
        _require_zone(context, request.zone)
        df = get_prices_as_of(
            request.zone,
            _ts_to_dt(request.start),
            _ts_to_dt(request.end),
            _ts_to_dt(request.as_of),
        ).reset_index()
        return prices_pb2.PriceResponse(
            rows=[
                prices_pb2.PriceRow(valid_time=_dt_to_ts(row.valid_time), value=row.value)
                for row in df.itertuples(index=False)
            ]
        )

    def GetRevisions(self, request, context):
        _require_zone(context, request.zone)
        df = get_price_revisions(
            request.zone, _ts_to_dt(request.start), _ts_to_dt(request.end)
        ).reset_index()
        df = df.sort_values(["valid_time", "knowledge_time"])
        return prices_pb2.RevisionResponse(
            rows=[
                prices_pb2.RevisionRow(
                    valid_time=_dt_to_ts(row.valid_time),
                    knowledge_time=_dt_to_ts(row.knowledge_time),
                    value=row.value,
                )
                for row in df.itertuples(index=False)
            ]
        )


def build_server(host: str = "127.0.0.1", port: int = 50051) -> tuple[grpc.Server, int]:
    """Build a gRPC server with reflection enabled. Port 0 binds to a random free port."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    prices_pb2_grpc.add_PriceServiceServicer_to_server(PriceService(), server)

    service_names = (
        prices_pb2.DESCRIPTOR.services_by_name["PriceService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    bound_port = server.add_insecure_port(f"{host}:{port}")
    return server, bound_port


def serve(host: str = "127.0.0.1", port: int = 50051) -> None:
    """Run the gRPC server until interrupted."""
    server, _ = build_server(host, port)
    server.start()
    server.wait_for_termination()
