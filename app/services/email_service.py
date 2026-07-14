import asyncio
import html
import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def escape_html(value: Any, fallback: str = "-") -> str:
    """
    تحويل أي قيمة إلى نص آمن للاستخدام داخل HTML.
    """
    if value is None or value == "":
        return html.escape(fallback)

    return html.escape(str(value))


def format_money(value: Any) -> str:
    """
    تنسيق السعر مع حماية من القيم الفارغة أو غير الصحيحة.
    """
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def build_items_rows(order_data: dict) -> str:
    """
    إنشاء صفوف جدول المنتجات داخل الإيميل.
    """
    items = order_data.get("items") or []

    if not items:
        return """
        <tr>
            <td colspan="5" style="padding:16px;text-align:center;">
                لا توجد تفاصيل منتجات.
            </td>
        </tr>
        """

    rows = []

    for item in items:
        product_name = escape_html(
            item.get("product_name")
            or item.get("name")
            or f"منتج رقم {item.get('product_id', '-')}"
        )

        try:
            quantity = int(item.get("quantity") or 1)
        except (TypeError, ValueError):
            quantity = 1

        unit_price = item.get("unit_price") or item.get("price") or 0

        item_total = item.get("total_price")

        if item_total is None:
            try:
                item_total = float(unit_price or 0) * quantity
            except (TypeError, ValueError):
                item_total = 0

        rows.append(
            f"""
            <tr>
                <td style="padding:12px;border-bottom:1px solid #eeeeee;">
                    {product_name}
                </td>

                <td style="padding:12px;border-bottom:1px solid #eeeeee;text-align:center;">
                    {quantity}
                </td>

                <td style="padding:12px;border-bottom:1px solid #eeeeee;text-align:center;">
                    {format_money(unit_price)} جنيه
                </td>

                <td style="padding:12px;border-bottom:1px solid #eeeeee;text-align:center;">
                    {format_money(item_total)} جنيه
                </td>
            </tr>
            """
        )

    return "".join(rows)


def build_admin_email(order_data: dict) -> str:
    """
    إيميل الأدمن عند وصول طلب جديد.
    """
    order_id = escape_html(order_data.get("id"), "جديد")
    customer_name = escape_html(order_data.get("customer_name"))
    customer_email = escape_html(order_data.get("customer_email"))
    phone = escape_html(order_data.get("phone"))
    governorate = escape_html(order_data.get("governorate"))
    address = escape_html(order_data.get("address"))
    note = escape_html(order_data.get("note"), "لا توجد ملاحظات")
    coupon_code = escape_html(order_data.get("coupon_code"), "لا يوجد")
    payment_method = escape_html(
        order_data.get("payment_method"),
        "لم يتم تحديدها",
    )

    items_rows = build_items_rows(order_data)

    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>

    <body style="
        margin:0;
        padding:0;
        background:#f6f6f6;
        font-family:Arial,Tahoma,sans-serif;
        color:#222222;
    ">
        <div style="
            max-width:700px;
            margin:30px auto;
            background:#ffffff;
            border-radius:12px;
            overflow:hidden;
            border:1px solid #eeeeee;
        ">
            <div style="
                background:#892047;
                color:#ffffff;
                padding:24px;
                text-align:center;
            ">
                <h1 style="margin:0;font-size:26px;">
                    طلب جديد من UNIQARE
                </h1>

                <p style="margin:10px 0 0;">
                    رقم الطلب: #{order_id}
                </p>
            </div>

            <div style="padding:24px;">
                <h2 style="color:#892047;margin-top:0;">
                    بيانات العميل
                </h2>

                <table style="
                    width:100%;
                    border-collapse:collapse;
                    background:#fafafa;
                    margin-bottom:25px;
                ">
                    <tr>
                        <td style="padding:10px;font-weight:bold;">الاسم</td>
                        <td style="padding:10px;">{customer_name}</td>
                    </tr>

                    <tr>
                        <td style="padding:10px;font-weight:bold;">رقم الهاتف</td>
                        <td style="padding:10px;">{phone}</td>
                    </tr>

                    <tr>
                        <td style="padding:10px;font-weight:bold;">الإيميل</td>
                        <td style="padding:10px;">{customer_email}</td>
                    </tr>

                    <tr>
                        <td style="padding:10px;font-weight:bold;">المحافظة</td>
                        <td style="padding:10px;">{governorate}</td>
                    </tr>

                    <tr>
                        <td style="padding:10px;font-weight:bold;">العنوان</td>
                        <td style="padding:10px;">{address}</td>
                    </tr>

                    <tr>
                        <td style="padding:10px;font-weight:bold;">ملاحظات</td>
                        <td style="padding:10px;">{note}</td>
                    </tr>
                </table>

                <h2 style="color:#892047;">
                    المنتجات
                </h2>

                <div style="overflow-x:auto;">
                    <table style="
                        width:100%;
                        border-collapse:collapse;
                        border:1px solid #eeeeee;
                    ">
                        <thead>
                            <tr style="background:#f2e6ea;">
                                <th style="padding:12px;text-align:right;">
                                    المنتج
                                </th>

                                <th style="padding:12px;">
                                    الكمية
                                </th>

                                <th style="padding:12px;">
                                    سعر القطعة
                                </th>

                                <th style="padding:12px;">
                                    الإجمالي
                                </th>
                            </tr>
                        </thead>

                        <tbody>
                            {items_rows}
                        </tbody>
                    </table>
                </div>

                <div style="
                    margin-top:25px;
                    background:#fafafa;
                    padding:18px;
                    border-radius:10px;
                ">
                    <p>
                        <strong>الإجمالي قبل الخصم:</strong>
                        {format_money(order_data.get("subtotal_price"))} جنيه
                    </p>

                    <p>
                        <strong>قيمة الخصم:</strong>
                        {format_money(order_data.get("discount_amount"))} جنيه
                    </p>

                    <p>
                        <strong>كود الخصم:</strong>
                        {coupon_code}
                    </p>

                    <p style="
                        font-size:20px;
                        color:#892047;
                        margin-bottom:0;
                    ">
                        <strong>الإجمالي النهائي:</strong>
                        {format_money(order_data.get("total_price"))} جنيه
                    </p>

                    <p>
                        <strong>طريقة الدفع:</strong>
                        {payment_method}
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


def build_customer_email(order_data: dict) -> str:
    """
    إيميل تأكيد الطلب للعميل.
    """
    order_id = escape_html(order_data.get("id"), "جديد")
    customer_name = escape_html(
        order_data.get("customer_name"),
        "عميلنا العزيز",
    )

    governorate = escape_html(order_data.get("governorate"))
    address = escape_html(order_data.get("address"))
    payment_method = escape_html(
        order_data.get("payment_method"),
        "لم يتم تحديدها",
    )

    items_rows = build_items_rows(order_data)

    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>

    <body style="
        margin:0;
        padding:0;
        background:#f6f6f6;
        font-family:Arial,Tahoma,sans-serif;
        color:#222222;
    ">
        <div style="
            max-width:700px;
            margin:30px auto;
            background:#ffffff;
            border-radius:12px;
            overflow:hidden;
            border:1px solid #eeeeee;
        ">
            <div style="
                background:#892047;
                color:#ffffff;
                padding:26px;
                text-align:center;
            ">
                <h1 style="margin:0;">
                    UNIQARE
                </h1>

                <p style="margin:10px 0 0;">
                    تم استلام طلبك بنجاح
                </p>
            </div>

            <div style="padding:26px;">
                <h2 style="color:#892047;">
                    أهلًا {customer_name} 👋
                </h2>

                <p style="line-height:1.8;">
                    شكرًا لطلبك من UNIQARE.
                    تم تسجيل طلبك بنجاح وسيقوم فريقنا بمراجعته
                    والتواصل معك عند الحاجة.
                </p>

                <div style="
                    background:#f2e6ea;
                    padding:16px;
                    border-radius:10px;
                    margin:20px 0;
                    text-align:center;
                ">
                    <strong>
                        رقم الطلب: #{order_id}
                    </strong>
                </div>

                <h2 style="color:#892047;">
                    تفاصيل طلبك
                </h2>

                <div style="overflow-x:auto;">
                    <table style="
                        width:100%;
                        border-collapse:collapse;
                        border:1px solid #eeeeee;
                    ">
                        <thead>
                            <tr style="background:#f2e6ea;">
                                <th style="padding:12px;text-align:right;">
                                    المنتج
                                </th>

                                <th style="padding:12px;">
                                    الكمية
                                </th>

                                <th style="padding:12px;">
                                    سعر القطعة
                                </th>

                                <th style="padding:12px;">
                                    الإجمالي
                                </th>
                            </tr>
                        </thead>

                        <tbody>
                            {items_rows}
                        </tbody>
                    </table>
                </div>

                <div style="
                    margin-top:25px;
                    background:#fafafa;
                    padding:18px;
                    border-radius:10px;
                ">
                    <p>
                        <strong>الإجمالي قبل الخصم:</strong>
                        {format_money(order_data.get("subtotal_price"))} جنيه
                    </p>

                    <p>
                        <strong>قيمة الخصم:</strong>
                        {format_money(order_data.get("discount_amount"))} جنيه
                    </p>

                    <p style="
                        color:#892047;
                        font-size:20px;
                    ">
                        <strong>الإجمالي النهائي:</strong>
                        {format_money(order_data.get("total_price"))} جنيه
                    </p>

                    <p>
                        <strong>طريقة الدفع:</strong>
                        {payment_method}
                    </p>

                    <p>
                        <strong>عنوان التوصيل:</strong>
                        {governorate} - {address}
                    </p>
                </div>

                <p style="
                    margin-top:25px;
                    line-height:1.8;
                    text-align:center;
                ">
                    شكرًا لاختيارك UNIQARE 🤍
                </p>
            </div>
        </div>
    </body>
    </html>
    """


async def send_brevo_email(
    recipient_email: str,
    recipient_name: str,
    subject: str,
    html_content: str,
) -> bool:
    """
    إرسال إيميل واحد عن طريق Brevo API.
    يتم عمل 3 محاولات في حالة حدوث خطأ مؤقت.
    """
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    sender_name = os.getenv("BREVO_SENDER_NAME", "UNIQARE")

    if not api_key:
        logger.error("BREVO_API_KEY is missing.")
        return False

    if not sender_email:
        logger.error("BREVO_SENDER_EMAIL is missing.")
        return False

    if not recipient_email:
        logger.warning("Recipient email is empty.")
        return False

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email,
        },
        "to": [
            {
                "name": recipient_name or "Customer",
                "email": recipient_email,
            }
        ],
        "subject": subject,
        "htmlContent": html_content,
    }

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": api_key,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        for attempt in range(1, 4):
            try:
                response = await client.post(
                    BREVO_API_URL,
                    headers=headers,
                    json=payload,
                )

                if 200 <= response.status_code < 300:
                    logger.info(
                        "Brevo email sent successfully to %s",
                        recipient_email,
                    )
                    return True

                logger.error(
                    "Brevo error. Status: %s Response: %s",
                    response.status_code,
                    response.text,
                )

            except httpx.TimeoutException:
                logger.error(
                    "Brevo request timed out. Attempt %s",
                    attempt,
                )

            except httpx.RequestError as error:
                logger.error(
                    "Brevo network error on attempt %s: %s",
                    attempt,
                    error,
                )

            except Exception:
                logger.exception(
                    "Unexpected email error on attempt %s",
                    attempt,
                )

            if attempt < 3:
                await asyncio.sleep(attempt * 2)

    return False


async def send_order_emails(order_data: dict) -> None:
    """
    إرسال إيميل الأدمن ثم إيميل العميل.

    أي خطأ هنا لا يلغي الأوردر لأن الوظيفة تعمل
    بعد حفظ الأوردر كـ Background Task.
    """
    admin_email = os.getenv("ADMIN_EMAIL")
    store_name = os.getenv("BREVO_SENDER_NAME", "UNIQARE")

    order_id = order_data.get("id", "جديد")
    customer_name = str(
        order_data.get("customer_name") or "عميل جديد"
    )

    # إيميل الأدمن
    if admin_email:
        await send_brevo_email(
            recipient_email=admin_email,
            recipient_name="UNIQARE Admin",
            subject=f"طلب جديد #{order_id} - {store_name}",
            html_content=build_admin_email(order_data),
        )
    else:
        logger.error(
            "ADMIN_EMAIL is missing. Admin email was not sent."
        )

    # إيميل العميل
    customer_email = str(
        order_data.get("customer_email") or ""
    ).strip()

    if customer_email:
        await send_brevo_email(
            recipient_email=customer_email,
            recipient_name=customer_name,
            subject=f"تم استلام طلبك #{order_id} - {store_name}",
            html_content=build_customer_email(order_data),
        )
    else:
        logger.warning(
            "Order %s has no customer email. "
            "Only the admin notification was attempted.",
            order_id,
        )