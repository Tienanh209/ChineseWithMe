"""Message texts, in the user's UI language (vi or en)."""

from urllib.parse import quote

from app.config import get_settings
from app.services.mailer import Mail


def _link(path: str, token: str) -> str:
    return f"{get_settings().public_url.rstrip('/')}{path}?token={quote(token)}"


def verify_email_mail(to: str, lang: str, token: str) -> Mail:
    url = _link("/verify-email", token)
    if lang == "en":
        return Mail(
            to,
            "Confirm your email address",
            f"Welcome! Confirm your email address by opening this link:\n\n{url}\n\n"
            "The link works once and expires in 48 hours. If you did not sign up, ignore this email.\n",
        )
    return Mail(
        to,
        "Xác nhận địa chỉ email của bạn",
        f"Chào mừng bạn! Hãy xác nhận email bằng cách mở liên kết sau:\n\n{url}\n\n"
        "Liên kết chỉ dùng một lần và hết hạn sau 48 giờ. Nếu bạn không đăng ký, hãy bỏ qua email này.\n",
    )


def reset_password_mail(to: str, lang: str, token: str) -> Mail:
    url = _link("/reset-password", token)
    if lang == "en":
        return Mail(
            to,
            "Reset your password",
            f"Open this link to choose a new password:\n\n{url}\n\n"
            "The link works once and expires in 1 hour. If you did not ask for this, ignore this email; "
            "your password stays the same.\n",
        )
    return Mail(
        to,
        "Đặt lại mật khẩu",
        f"Mở liên kết sau để chọn mật khẩu mới:\n\n{url}\n\n"
        "Liên kết chỉ dùng một lần và hết hạn sau 1 giờ. Nếu bạn không yêu cầu, hãy bỏ qua email này; "
        "mật khẩu của bạn không thay đổi.\n",
    )
