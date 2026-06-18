@test_static_typing.py -> check if there are pytest plugins or other SOTA patterns instead of homebrewing using `uv run`

def test_duplicate_type_uri_is_rejected() -> I'd prefer to raise at runtime, e.g. when building the openapi docs. There should be no need to have a global registry, unless we can't build the exception handlers and openapi adjustments at ``add_problem_handlers`` time. If the registry serves no other prupose than raising an error on definition time, remove and replace with runtime error!

use / verify  against "/testing-fastapi-endpoints" skill

All imports MUST be at the module level unless there is a very good argument against it (fix e.g. import json, ...)

The examples should include multiple error types on one endpoint to show union there and in openapi docs.

e.g. `/docs#/default/get_post_posts__post_id__get` in `examples/` shows "422 Validation Error with `application/json` instead of RFC 9457's `application/problem+json`. On `403 The account does not have enough credit` there is `"additionalProp1": {}` - why? Type is `"type": "about:blank",` altough there is `http://localhost:4545/problems/out-of-credit`. docs and /problems/<...> contains the built-in errors like `not-authenticated` which could be confusing if using on apps that e.g. have no auth layer and are only used in an isolated network.

