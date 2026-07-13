from ninja import Schema


class CredentialsIn(Schema):
    email: str
    password: str


class UserOut(Schema):
    id: int
    email: str

    @staticmethod
    def resolve_email(obj):
        # Usuarios creados por register guardan el email también como username;
        # para cuentas viejas (createsuperuser) puede faltar el campo email.
        return obj.email or obj.username


class SessionOut(Schema):
    authenticated: bool
    user: UserOut | None = None


class MessageOut(Schema):
    detail: str
