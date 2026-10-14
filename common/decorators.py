from django.contrib.auth.decorators import user_passes_test

def role_required(*roles):
    def check(user):
        if not user.is_authenticated: return False
        if user.is_superuser: return True
        return any(getattr(user, f"is_{role.lower()}", False) for role in roles)
    return user_passes_test(check, login_url="login")

def admin_required(view): return role_required("admin")(view)
def office_required(view): return role_required("admin", "secretary")(view)
