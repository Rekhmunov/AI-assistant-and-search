from app.schemas.admin import UserAdminUpdate


def test_user_admin_update_accepts_password():
    body = UserAdminUpdate(password="newpassword1")
    assert body.password == "newpassword1"
