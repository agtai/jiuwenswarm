"""Speech binding adapter for the shared Host authority service."""
from __future__ import annotations
from .batch_speech import SpeechAuthorizationBinding
from jiuwenswarm.server.runtime.authority.product_authority import (
    ProductAuthorityService, _input_error, _normalize_scope, _require_text,
    AuthorityResourceBinding, _require_sha256, AuthorityRouteContext,
    ProductAuthorityRequest, ProductAuthorityInputError, _authorized_or_none,
)

class SpeechAuthorityResolverAdapter:
    """Implement the existing Speech resolver without accepting browser grants."""

    def __init__(self, service: ProductAuthorityService) -> None:
        if not isinstance(service, ProductAuthorityService):
            raise _input_error("speech_adapter.service")
        self._service = service

    def authorize(
        self, binding: SpeechAuthorizationBinding
    ) -> SpeechAuthorizationBinding | None:
        try:
            scope = _normalize_scope(binding.scope, "speech.scope")
            operation = _require_text(binding.operation, "speech.operation")
            resource = AuthorityResourceBinding(
                kind="speech.authorization",
                resource_id=_require_text(binding.operation_id, "speech.operation_id"),
                fingerprint_sha256=_require_sha256(
                    binding.content_sha256, "speech.content_sha256"
                ),
            )
            route = AuthorityRouteContext(
                session_id=_require_text(scope.session_id, "speech.session_id"),
                correlation_id=_require_text(
                    binding.correlation_id, "speech.correlation_id"
                ),
                claimed_user_id=_require_text(binding.subject_id, "speech.subject_id"),
                claimed_project_id=scope.project_id,
                claimed_scope=scope,
            )
            request = ProductAuthorityRequest(
                route=route,
                operation=operation,
                required_capabilities=frozenset({operation}),
                resource=resource,
            )
        except (AttributeError, ProductAuthorityInputError, TypeError):
            return None
        authority = _authorized_or_none(self._service.resolve(request))
        if authority is None:
            return None
        return binding
