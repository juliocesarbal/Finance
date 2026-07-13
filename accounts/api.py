"""Autenticación por sesión de Django: registro, login, logout y sesión actual.

El identificador de acceso es el **email** (se persiste también como username
del User estándar de Django, que admite ``@``/``.``). No hay modelo propio:
se reusa ``django.contrib.auth`` tal como ya lo hace /admin.

CSRF: los routers protegidos con ``django_auth`` lo validan solos (Ninja).
Login y register son anónimos, así que lo exigimos a mano con ``check_csrf``;
la cookie ``csrftoken`` se garantiza en ``GET /auth/me`` (el frontend la lee
y la manda como header ``X-CSRFToken`` en toda mutación).
"""
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.middleware.csrf import get_token
from ninja import Router
from ninja.errors import HttpError
from ninja.security import django_auth
from ninja.utils import check_csrf

from .schemas import CredentialsIn, MessageOut, SessionOut, UserOut

router = Router()

# El username de Django tope en 150 caracteres y acá guarda el email.
EMAIL_MAX_LENGTH = 150


def _enforce_csrf(request):
    if check_csrf(request) is not None:
        raise HttpError(
            403, "Falta el token CSRF: pedí GET /api/auth/me y reenviá la cookie."
        )


def _clean_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > EMAIL_MAX_LENGTH:
        raise ValidationError("Correo demasiado largo.")
    validate_email(email)
    return email


@router.get("/me", response=SessionOut)
def me(request):
    """Sesión actual. Siempre deja lista la cookie CSRF para el frontend."""
    get_token(request)
    if request.user.is_authenticated:
        return {"authenticated": True, "user": request.user}
    return {"authenticated": False, "user": None}


@router.post("/register", response={200: UserOut, 400: MessageOut})
def register(request, payload: CredentialsIn):
    """Crea la cuenta y deja la sesión iniciada (sin verificación de email)."""
    _enforce_csrf(request)
    try:
        email = _clean_email(payload.email)
    except ValidationError:
        return 400, {"detail": "Ingresá un correo electrónico válido."}

    User = get_user_model()
    if User.objects.filter(username__iexact=email).exists():
        return 400, {"detail": "Ya existe una cuenta con ese correo."}

    try:
        validate_password(payload.password, user=User(username=email, email=email))
    except ValidationError as exc:
        return 400, {"detail": " ".join(exc.messages)}

    user = User.objects.create_user(username=email, email=email, password=payload.password)
    login(request, user)
    return user


@router.post("/login", response={200: UserOut, 401: MessageOut})
def login_view(request, payload: CredentialsIn):
    _enforce_csrf(request)
    email = payload.email.strip().lower()
    user = authenticate(request, username=email, password=payload.password)
    if user is None:
        return 401, {"detail": "Correo o contraseña incorrectos."}
    login(request, user)
    return user


@router.post("/logout", response={204: None}, auth=django_auth)
def logout_view(request):
    logout(request)
    return 204, None
