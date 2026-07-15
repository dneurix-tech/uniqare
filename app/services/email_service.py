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


def normalize_email(value: Any) -> str:
    """
    تنظيف عنوان البريد وتوحيده بحروف صغيرة حتى يطابق
    عنوان الـSender الموثق داخل Brevo.
    """
    return str(value or "").strip().lower()


async def send_brevo_email(
    recipient_email: str,
    recipient_name: str,
    subject: str,
    html_content: str,
) -> bool:
    """
    إرسال رسالة واحدة من خلال Brevo Transactional API.

    True تعني أن Brevo قبل طلب الإرسال وأرجع messageId.
    التسليم النهائي يُراجع من Transactional > Logs في Brevo.
    """
    api_key = str(
        os.getenv("BREVO_API_KEY") or ""
    ).strip()

    sender_email = normalize_email(
        os.getenv("BREVO_SENDER_EMAIL")
    )

    sender_name = str(
        os.getenv("BREVO_SENDER_NAME") or "UNIQARE"
    ).strip()

    clean_recipient_email = normalize_email(
        recipient_email
    )

    clean_recipient_name = str(
        recipient_name or "Customer"
    ).strip()

    clean_subject = str(
        subject or "UNIQARE"
    ).strip()

    print(
        "BREVO SEND REQUEST:",
        {
            "sender": sender_email,
            "recipient": clean_recipient_email,
            "subject": clean_subject,
        },
        flush=True,
    )

    if not api_key:
        print(
            "BREVO CONFIG ERROR: BREVO_API_KEY is missing.",
            flush=True,
        )
        return False

    if not sender_email:
        print(
            "BREVO CONFIG ERROR: "
            "BREVO_SENDER_EMAIL is missing.",
            flush=True,
        )
        return False

    if not clean_recipient_email:
        print(
            "BREVO CONFIG ERROR: Recipient email is empty.",
            flush=True,
        )
        return False

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email,
        },
        "to": [
            {
                "name": clean_recipient_name,
                "email": clean_recipient_email,
            }
        ],
        "subject": clean_subject,
        "htmlContent": html_content,
    }

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": api_key,
    }

    # نعيد المحاولة فقط مع الأخطاء المؤقتة:
    # Rate limit أو أخطاء سيرفر Brevo.
    retryable_status_codes = {
        408,
        425,
        429,
        500,
        502,
        503,
        504,
    }

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0),
    ) as client:
        for attempt in range(1, 4):
            try:
                response = await client.post(
                    BREVO_API_URL,
                    headers=headers,
                    json=payload,
                )

                if 200 <= response.status_code < 300:
                    try:
                        response_data = response.json()
                    except ValueError:
                        response_data = {
                            "raw_response": response.text
                        }

                    print(
                        "BREVO REQUEST ACCEPTED:",
                        {
                            "recipient": clean_recipient_email,
                            "status": response.status_code,
                            "response": response_data,
                        },
                        flush=True,
                    )
                    return True

                print(
                    "BREVO API ERROR:",
                    {
                        "attempt": attempt,
                        "status": response.status_code,
                        "response": response.text,
                        "sender": sender_email,
                        "recipient": clean_recipient_email,
                    },
                    flush=True,
                )

                # أخطاء 400/401/403 وغيرها غالبًا إعدادات خاطئة،
                # لذلك لا فائدة من تكرار نفس الطلب ثلاث مرات.
                if (
                    response.status_code
                    not in retryable_status_codes
                ):
                    return False

            except httpx.TimeoutException as error:
                print(
                    "BREVO TIMEOUT:",
                    {
                        "attempt": attempt,
                        "error": str(error),
                    },
                    flush=True,
                )

            except httpx.RequestError as error:
                print(
                    "BREVO NETWORK ERROR:",
                    {
                        "attempt": attempt,
                        "error": str(error),
                    },
                    flush=True,
                )

            except Exception as error:
                print(
                    "BREVO UNEXPECTED ERROR:",
                    {
                        "attempt": attempt,
                        "error": repr(error),
                    },
                    flush=True,
                )
                return False

            if attempt < 3:
                await asyncio.sleep(attempt * 2)

    return False


async def send_order_emails(
    order_data: dict,
) -> None:
    """
    إرسال إشعار للأدمن وتأكيد للعميل بعد حفظ الطلب.

    فشل إرسال أي رسالة لا يلغي الطلب؛ لأن الدالة تعمل
    من خلال FastAPI BackgroundTasks.
    """
    order_id = order_data.get("id", "جديد")

    admin_email = normalize_email(
        os.getenv("ADMIN_EMAIL")
    )

    store_name = str(
        os.getenv("BREVO_SENDER_NAME") or "UNIQARE"
    ).strip()

    customer_name = str(
        order_data.get("customer_name")
        or "عميل جديد"
    ).strip()

    customer_email = normalize_email(
        order_data.get("customer_email")
        or order_data.get("email")
    )

    print(
        f"EMAIL TASK STARTED FOR ORDER #{order_id}",
        flush=True,
    )

    print(
        "EMAIL TASK RECIPIENTS:",
        {
            "admin": admin_email,
            "customer": customer_email,
        },
        flush=True,
    )

    admin_result = False
    customer_result = False

    # إيميل الأدمن
    if admin_email:
        admin_result = await send_brevo_email(
            recipient_email=admin_email,
            recipient_name="UNIQARE Admin",
            subject=(
                f"طلب جديد #{order_id} - {store_name}"
            ),
            html_content=build_admin_email(
                order_data
            ),
        )
    else:
        print(
            "ADMIN EMAIL SKIPPED: ADMIN_EMAIL is missing.",
            flush=True,
        )

    # إيميل العميل
    if customer_email:
        customer_result = await send_brevo_email(
            recipient_email=customer_email,
            recipient_name=customer_name,
            subject=(
                f"تم استلام طلبك #{order_id} - "
                f"{store_name}"
            ),
            html_content=build_customer_email(
                order_data
            ),
        )
    else:
        print(
            f"CUSTOMER EMAIL SKIPPED FOR ORDER #{order_id}: "
            "customer email is missing.",
            flush=True,
        )

    print(
        f"EMAIL TASK FINISHED FOR ORDER #{order_id}:",
        {
            "admin_accepted_by_brevo": admin_result,
            "customer_accepted_by_brevo": customer_result,
        },
        flush=True,
    )