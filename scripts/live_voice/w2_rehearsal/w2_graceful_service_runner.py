from __future__ import annotations

import argparse
import asyncio
import signal
from collections.abc import Awaitable, Callable


ServiceFactory = Callable[[], Awaitable[None]]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a W2 rehearsal service with cooperative Windows shutdown."
    )
    subparsers = parser.add_subparsers(dest="service", required=True)

    agentserver = subparsers.add_parser("agentserver")
    agentserver.add_argument("--host", default="127.0.0.1")
    agentserver.add_argument("--port", type=int, required=True)

    gateway = subparsers.add_parser("gateway")
    gateway.add_argument("--agent-server-url", required=True)
    gateway.add_argument("--host", default="127.0.0.1")
    gateway.add_argument("--port", type=int, required=True)
    gateway.add_argument("--web-path", default="/ws")
    return parser


def _service_factory(args: argparse.Namespace) -> ServiceFactory:
    if args.service == "agentserver":
        from jiuwenswarm.server import app_agentserver

        app_agentserver.install_async_dump_handler("agentserver")
        return lambda: app_agentserver._run(host=args.host, port=args.port)

    from jiuwenswarm.gateway import app_gateway

    app_gateway.install_async_dump_handler("gateway")
    return lambda: app_gateway._run(
        agent_server_url=args.agent_server_url,
        web_host=args.host,
        web_port=args.port,
        web_path=args.web_path,
    )


async def _run(factory: ServiceFactory) -> None:
    loop = asyncio.get_running_loop()
    stop_requested = asyncio.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        loop.call_soon_threadsafe(stop_requested.set)

    handled_signals = [signal.SIGINT, signal.SIGTERM]
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        handled_signals.append(sigbreak)
    previous_handlers: dict[int, object] = {}
    for handled_signal in handled_signals:
        previous_handlers[handled_signal] = signal.signal(handled_signal, request_stop)

    service_task = asyncio.create_task(factory(), name="w2-rehearsal-service")
    stop_task = asyncio.create_task(
        stop_requested.wait(), name="w2-rehearsal-stop-request"
    )
    try:
        done, _pending = await asyncio.wait(
            {service_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if service_task in done:
            stop_task.cancel()
            await service_task
            return
        service_task.cancel()
        try:
            await service_task
        except asyncio.CancelledError:
            pass
    finally:
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass
        for handled_signal, previous_handler in previous_handlers.items():
            signal.signal(handled_signal, previous_handler)


def main() -> int:
    args = _parser().parse_args()
    asyncio.run(_run(_service_factory(args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
