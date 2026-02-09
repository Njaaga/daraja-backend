import secrets
from django.shortcuts import redirect
from django.conf import settings
from django.contrib.auth.decorators import login_required


@login_required
def quickbooks_connect(request):
    state = secrets.token_urlsafe(32)
    request.session["qb_oauth_state"] = state

    url = (
        "https://appcenter.intuit.com/connect/oauth2"
        f"?client_id={settings.QB_CLIENT_ID}"
        f"&response_type=code"
        f"&scope=com.intuit.quickbooks.accounting"
        f"&redirect_uri={settings.QB_REDIRECT_URI}"
        f"&state={state}"
    )

    return redirect(url)
