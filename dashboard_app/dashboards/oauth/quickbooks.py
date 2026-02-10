from django.http import JsonResponse

def quickbooks_connect(request):
    return JsonResponse({"ok": True})

def quickbooks_callback(request):
    return JsonResponse({"ok": True})
