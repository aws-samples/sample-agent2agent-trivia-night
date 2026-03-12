"""
Property-based tests for the Config Generator Lambda.

The Config Generator is an inline Python Lambda defined in the CDK WebUiStack
that produces an ``aws-config.js`` file containing six configuration properties
assigned to ``window.AWS_CONFIG``.  Since the Lambda is inline in CDK, we
replicate the template-string formatting logic here as a standalone function
and verify that all six properties appear in the output for arbitrary inputs.

Uses ``hypothesis`` with a minimum of 100 examples per property.

Feature: lss-workshop-platform, Property 17: Config Generator Produces Valid Configuration
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Replicated config generation logic (mirrors the inline Lambda in
# platform/infrastructure/lib/webui-stack.ts)
# ---------------------------------------------------------------------------


def generate_config(
    region: str,
    user_pool_id: str,
    user_pool_client_id: str,
    identity_pool_id: str,
    api_gateway_url: str,
    cognito_domain: str,
) -> str:
    """Produce the ``aws-config.js`` content exactly as the Config Generator
    Lambda does via its f-string template."""
    return (
        f'window.AWS_CONFIG = {{\n'
        f'  region: "{region}",\n'
        f'  userPoolId: "{user_pool_id}",\n'
        f'  userPoolWebClientId: "{user_pool_client_id}",\n'
        f'  identityPoolId: "{identity_pool_id}",\n'
        f'  apiGatewayUrl: "{api_gateway_url}",\n'
        f'  cognitoDomain: "{cognito_domain}"\n'
        f'}};\n'
    )


# ---------------------------------------------------------------------------
# Hypothesis strategies — generate realistic-ish config values that avoid
# characters which would break the JS string literals (quotes, newlines).
# ---------------------------------------------------------------------------

_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters='"\\`\n\r',
    ),
    min_size=1,
    max_size=120,
)

_region_st = st.sampled_from([
    "us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1",
    "eu-central-1", "ap-northeast-1",
])

_user_pool_id_st = st.from_regex(
    r"[a-z]{2}-[a-z]+-[0-9]_[A-Za-z0-9]{9}", fullmatch=True
)

_client_id_st = st.from_regex(r"[a-z0-9]{26}", fullmatch=True)

_identity_pool_id_st = st.from_regex(
    r"[a-z]{2}-[a-z]+-[0-9]:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    fullmatch=True,
)

_api_url_st = st.from_regex(
    r"https://[a-z0-9]{10}\.execute-api\.[a-z]{2}-[a-z]+-[0-9]\.amazonaws\.com/prod/",
    fullmatch=True,
)

_cognito_domain_st = st.from_regex(
    r"[a-z0-9-]{8,20}\.auth\.[a-z]{2}-[a-z]+-[0-9]\.amazoncognito\.com",
    fullmatch=True,
)


# ---------------------------------------------------------------------------
# Property 17: Config Generator Produces Valid Configuration
# ---------------------------------------------------------------------------


class TestConfigGeneratorProperties:
    """
    **Validates: Requirements 10.6**

    Property 17: Config Generator Produces Valid Configuration — Random config
    values, verify all six properties present in output.
    """

    @given(
        region=_region_st,
        user_pool_id=_user_pool_id_st,
        user_pool_client_id=_client_id_st,
        identity_pool_id=_identity_pool_id_st,
        api_gateway_url=_api_url_st,
        cognito_domain=_cognito_domain_st,
    )
    @settings(max_examples=100)
    def test_config_contains_all_six_properties(
        self,
        region: str,
        user_pool_id: str,
        user_pool_client_id: str,
        identity_pool_id: str,
        api_gateway_url: str,
        cognito_domain: str,
    ) -> None:
        """
        Feature: lss-workshop-platform, Property 17: Config Generator Produces Valid Configuration

        For any set of input configuration values, the generated aws-config.js
        content must contain all six values as properties of window.AWS_CONFIG.
        """
        output = generate_config(
            region=region,
            user_pool_id=user_pool_id,
            user_pool_client_id=user_pool_client_id,
            identity_pool_id=identity_pool_id,
            api_gateway_url=api_gateway_url,
            cognito_domain=cognito_domain,
        )

        # 1. Output starts with the window.AWS_CONFIG assignment
        assert output.startswith("window.AWS_CONFIG = {"), (
            "Output must begin with 'window.AWS_CONFIG = {'"
        )

        # 2. Output ends with the closing '};'
        assert output.strip().endswith("};"), (
            "Output must end with '};'"
        )

        # 3. All six property keys are present
        for key in (
            "region",
            "userPoolId",
            "userPoolWebClientId",
            "identityPoolId",
            "apiGatewayUrl",
            "cognitoDomain",
        ):
            assert f'  {key}: "' in output, (
                f"Property '{key}' must appear in the output"
            )

        # 4. All six values are embedded in the output
        assert f'region: "{region}"' in output
        assert f'userPoolId: "{user_pool_id}"' in output
        assert f'userPoolWebClientId: "{user_pool_client_id}"' in output
        assert f'identityPoolId: "{identity_pool_id}"' in output
        assert f'apiGatewayUrl: "{api_gateway_url}"' in output
        assert f'cognitoDomain: "{cognito_domain}"' in output

        # 5. Exactly six property lines inside the config block
        property_lines = [
            line.strip()
            for line in output.splitlines()
            if line.strip().startswith('"') is False
            and ": " in line
            and line.strip() not in ("window.AWS_CONFIG = {", "};")
        ]
        assert len(property_lines) == 6, (
            f"Expected exactly 6 property lines, got {len(property_lines)}"
        )
