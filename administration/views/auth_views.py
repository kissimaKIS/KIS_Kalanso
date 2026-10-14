from django.contrib import messages
from django.contrib.auth import login, logout, get_user_model
from django.shortcuts import redirect, render
from administration.forms import LoginForm


def login_view(request):
    if request.user.is_authenticated:
        return redirect("startup")

    form = LoginForm(request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("startup")

    return render(
        request,
        "registration/login.html",
        {"form": form},
    )


def bootstrap_admin(request):
    """
    Première installation :
    crée le tout premier compte administrateur depuis l'interface web.

    Dès qu'un utilisateur existe, cette route devient inaccessible.
    """
    User = get_user_model()

    if User.objects.exists():
        return redirect("login")

    error = None
    values = {}

    if request.method == "POST":
        values = {
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "username": request.POST.get("username", "").strip(),
            "email": request.POST.get("email", "").strip(),
        }

        password = request.POST.get("password", "")
        password_confirm = request.POST.get("password_confirm", "")

        if not values["first_name"] or not values["last_name"]:
            error = "Le prénom et le nom sont obligatoires."
        elif not values["username"]:
            error = "Le nom d'utilisateur est obligatoire."
        elif not password:
            error = "Le mot de passe est obligatoire."
        elif len(password) < 8:
            error = "Le mot de passe doit contenir au moins 8 caractères."
        elif password != password_confirm:
            error = "Les deux mots de passe ne correspondent pas."

        if not error:
            user = User.objects.create_superuser(
                username=values["username"],
                password=password,
                email=values["email"],
                first_name=values["first_name"],
                last_name=values["last_name"],
            )
            user.is_admin = True
            user.save(update_fields=["is_admin"])

            # Première installation : ouvrir directement la session du premier
            # administrateur. Il n'est pas nécessaire de repasser par l'écran
            # de connexion avant la configuration initiale.
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(
                request,
                "Compte administrateur créé. Bienvenue dans KIS Kalanso.",
            )
            return redirect("startup")

    return render(
        request,
        "registration/bootstrap.html",
        {
            "error": error,
            "values": values,
        },
    )


def logout_view(request):
    logout(request)
    messages.success(request, "Vous êtes déconnecté.")
    return redirect("login")
