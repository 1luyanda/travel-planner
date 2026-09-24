# Security

[Documentation index](README.md)

## API boundary

Protected API routes require one nonblank `X-API-Key` header matching the current or optional previous configured key using constant-time comparison. Missing key configuration returns 503; invalid/missing supplied keys return 401. Health is public.

The development Vite proxy inserts the key server-side. It is not an end-user identity or a browser secret. The application includes host validation, credentialed CORS for configured origins, and Pydantic validation. The body-size middleware checks Content-Length; it is not a streaming byte counter for bodies with no declared length.

Database/provider exceptions are mapped to generic service-unavailable errors in routes. Photo resource names are validated, and photo responses disable caching and MIME sniffing. This documentation describes implemented controls, not a penetration-test result.

## Accounts and sessions

Passwords use the installed pwdlib recommended Argon2 hashing implementation. Registration requires 12-128 characters; login permits 1-128 to validate submitted credentials. Duplicate registration returns 409; login failures use a generic message.

Stored email, normalized email, and display name are HMAC-SHA256 hashes. The identity key is `AUTH_SESSION_SECRET`, falling back to `API_AUTH_KEY` during service construction. Cookie operations still require `AUTH_SESSION_SECRET`. Changing the identity key changes email lookup hashes, and no migration/dual-key lookup is implemented.

Sessions contain user ID, email, display name, and expiry in a base64url payload signed with HMAC-SHA256. They are signed, not encrypted. Cookies are HttpOnly, SameSite=Lax, scoped to `/`, and Secure when configured. Default lifetime is one hour. Session validation verifies signature/expiry and resolves the stored user.

Logout clears the browser cookie; no server-side session revocation list is implemented. Registration uses the submitted display name in the session; login derives it from the email prefix because the original stored name is hashed.

Saved-flight and saved-activity routes derive user ID from the session, not a request-body user ID. The frontend gates Explore behind login, while its backing activity routes require only the proxy API key.

## Operational boundaries

Production mode requires a session secret of at least 32 characters and secure cookies and disables generated API documentation. It does not supply TLS termination, a production proxy, rate limiting, password reset, email verification, or multifactor authentication. There is no dedicated CSRF-token flow; cookie behavior uses SameSite=Lax.

Keep Cosmos, LLM, Google Places, API, and session secrets outside the frontend bundle and source control. No secret values are reproduced in this documentation.

Sources: [security helpers](../backend/security.py), [users](../backend/services/users.py), [identity hashing](../backend/services/identity.py), [settings](../backend/config.py), [middleware](../backend/main.py), [auth contracts](../backend/contracts/auth.py).
