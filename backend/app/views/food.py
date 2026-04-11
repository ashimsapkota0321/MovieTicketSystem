"""Food item management API views."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..models import Booking, BookingFoodItem, Combo, ComboItem, FoodItem, Order, OrderItem
from ..permissions import is_authenticated, resolve_customer, resolve_vendor, vendor_required
from ..utils import build_media_url


def _serialize_food_item(item: FoodItem, request: Any | None = None) -> dict[str, Any]:
    stock_quantity = int(item.stock_quantity or 0)
    sold_out_threshold = int(item.sold_out_threshold or 0)
    sold_out = bool(item.track_inventory and stock_quantity <= sold_out_threshold)
    stock_status = "SOLD_OUT" if sold_out else ("LOW_STOCK" if item.track_inventory and stock_quantity <= (sold_out_threshold + 10) else "IN_STOCK")
    image_url = build_media_url(request, getattr(item, "item_image", None))
    return {
        "id": item.id,
        "itemName": item.item_name,
        "category": item.category,
        "isVeg": bool(item.is_veg),
        "is_veg": bool(item.is_veg),
        "price": float(item.price),
        "isAvailable": bool(item.is_available),
        "trackInventory": bool(item.track_inventory),
        "stockQuantity": stock_quantity,
        "soldOutThreshold": sold_out_threshold,
        "soldOut": sold_out,
        "stockStatus": stock_status,
        "soldOutAt": item.sold_out_at.isoformat() if item.sold_out_at else None,
        "hall": item.hall,
        "vendorId": item.vendor_id,
        "imageUrl": image_url,
        "itemImage": image_url,
    }


def _to_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _get_uploaded_file(request: Any, *keys: str) -> Any:
    files = getattr(request, "FILES", None)
    if not files:
        return None
    for key in keys:
        if key in files:
            return files.get(key)
    return None


def _sync_food_item_availability(item: FoodItem) -> None:
    """Toggle availability based on tracked stock level and threshold."""
    if not item.track_inventory:
        return

    qty = int(item.stock_quantity or 0)
    threshold = int(item.sold_out_threshold or 0)
    if qty <= threshold:
        item.is_available = False
        if not item.sold_out_at:
            item.sold_out_at = timezone.now()
        return

    if item.sold_out_at:
        # Auto-restore availability only when inventory was previously auto-sold-out.
        item.is_available = True
        item.sold_out_at = None


def _serialize_combo(combo: Combo) -> dict[str, Any]:
    return {
        "id": combo.id,
        "name": combo.name,
        "description": combo.description,
        "comboPrice": float(combo.combo_price),
        "isAvailable": bool(combo.is_available),
        "hall": combo.hall,
        "vendorId": combo.vendor_id,
        "items": [
            {
                "foodItemId": combo_item.food_item_id,
                "foodItemName": combo_item.food_item.item_name,
                "quantity": int(combo_item.quantity),
            }
            for combo_item in combo.items.select_related("food_item").all()
        ],
    }


def _serialize_order(order: Order) -> dict[str, Any]:
    return {
        "id": order.id,
        "bookingId": order.booking_id,
        "userId": order.user_id,
        "vendorId": order.vendor_id,
        "status": order.status,
        "totalAmount": float(order.total_amount or 0),
        "createdAt": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "id": item.id,
                "type": "combo" if item.combo_id else "food_item",
                "foodItemId": item.food_item_id,
                "comboId": item.combo_id,
                "name": item.combo.name if item.combo_id and item.combo else (
                    item.food_item.item_name if item.food_item else None
                ),
                "quantity": int(item.quantity),
                "unitPrice": float(item.unit_price),
                "totalPrice": float(item.total_price),
            }
            for item in order.items.select_related("food_item", "combo").all()
        ],
    }


@api_view(["GET"])
def food_items(request: Any):
    """Return available food items for a vendor/cinema."""
    vendor_id = request.query_params.get("vendor_id") or request.query_params.get("vendorId")
    hall = (request.query_params.get("hall") or "").strip()

    queryset = FoodItem.objects.filter(is_available=True)
    if vendor_id:
        queryset = queryset.filter(vendor_id=vendor_id)
    if hall:
        queryset = queryset.filter(
            Q(hall__iexact=hall) | Q(hall__isnull=True) | Q(hall__exact="")
        )

    payload = [_serialize_food_item(item, request) for item in queryset.order_by("category", "item_name")]
    return Response({"items": payload}, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
@vendor_required
def vendor_food_items(request: Any):
    """List or create vendor-owned food items."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        items = FoodItem.objects.filter(vendor=vendor).order_by("-id")
        return Response({"items": [_serialize_food_item(item, request) for item in items]}, status=status.HTTP_200_OK)

    item_name = str(request.data.get("item_name") or request.data.get("itemName") or "").strip()
    category = str(request.data.get("category") or "").strip() or None
    is_veg_raw = request.data.get("is_veg")
    if is_veg_raw is None:
        is_veg_raw = request.data.get("isVeg")
    is_veg = _truthy(is_veg_raw, default=True)
    hall = str(request.data.get("hall") or "").strip() or None
    item_image = _get_uploaded_file(request, "item_image", "itemImage")
    price = _to_decimal(request.data.get("price"))
    track_inventory = _truthy(request.data.get("track_inventory", request.data.get("trackInventory")), default=False)
    stock_quantity = _to_int(request.data.get("stock_quantity", request.data.get("stockQuantity")))
    sold_out_threshold = _to_int(request.data.get("sold_out_threshold", request.data.get("soldOutThreshold")))
    is_available_raw = request.data.get("is_available")
    if is_available_raw is None:
        is_available_raw = request.data.get("isAvailable")
    is_available = _truthy(is_available_raw, default=True)

    if not item_name:
        return Response({"message": "item_name is required."}, status=status.HTTP_400_BAD_REQUEST)
    if price is None or price <= 0:
        return Response({"message": "price must be a positive number."}, status=status.HTTP_400_BAD_REQUEST)
    if stock_quantity is None:
        stock_quantity = 0
    if sold_out_threshold is None:
        sold_out_threshold = 0
    if stock_quantity < 0:
        return Response({"message": "stock_quantity must be zero or greater."}, status=status.HTTP_400_BAD_REQUEST)
    if sold_out_threshold < 0:
        return Response({"message": "sold_out_threshold must be zero or greater."}, status=status.HTTP_400_BAD_REQUEST)

    item = FoodItem(
        vendor=vendor,
        item_name=item_name,
        category=category,
        is_veg=is_veg,
        item_image=item_image,
        hall=hall,
        price=price,
        track_inventory=track_inventory,
        stock_quantity=stock_quantity,
        sold_out_threshold=sold_out_threshold,
        is_available=is_available,
    )
    _sync_food_item_availability(item)
    item.save()
    return Response({"item": _serialize_food_item(item, request)}, status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@vendor_required
def vendor_food_item_detail(request: Any, item_id: int):
    """Update or delete a vendor food item."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    item = FoodItem.objects.filter(pk=item_id, vendor=vendor).first()
    if not item:
        return Response({"message": "Food item not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        item.delete()
        return Response({"message": "Food item deleted."}, status=status.HTTP_200_OK)

    item_name = request.data.get("item_name")
    if item_name is None:
        item_name = request.data.get("itemName")
    if item_name is not None:
        next_name = str(item_name).strip()
        if not next_name:
            return Response({"message": "item_name cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        item.item_name = next_name

    if "category" in request.data:
        item.category = str(request.data.get("category") or "").strip() or None

    if "is_veg" in request.data or "isVeg" in request.data:
        raw = request.data.get("is_veg")
        if raw is None:
            raw = request.data.get("isVeg")
        item.is_veg = _truthy(raw, default=True)

    if "hall" in request.data:
        item.hall = str(request.data.get("hall") or "").strip() or None

    if "remove_image" in request.data or "removeImage" in request.data:
        raw = request.data.get("remove_image")
        if raw is None:
            raw = request.data.get("removeImage")
        if _truthy(raw, default=False):
            if item.item_image:
                item.item_image.delete(save=False)
            item.item_image = None

    uploaded_image = _get_uploaded_file(request, "item_image", "itemImage")
    if uploaded_image is not None:
        item.item_image = uploaded_image

    if "price" in request.data:
        next_price = _to_decimal(request.data.get("price"))
        if next_price is None or next_price <= 0:
            return Response({"message": "price must be a positive number."}, status=status.HTTP_400_BAD_REQUEST)
        item.price = next_price

    if "is_available" in request.data or "isAvailable" in request.data:
        raw = request.data.get("is_available")
        if raw is None:
            raw = request.data.get("isAvailable")
        item.is_available = _truthy(raw, default=True)

    if "track_inventory" in request.data or "trackInventory" in request.data:
        raw = request.data.get("track_inventory")
        if raw is None:
            raw = request.data.get("trackInventory")
        item.track_inventory = _truthy(raw, default=False)

    if "stock_quantity" in request.data or "stockQuantity" in request.data:
        raw = request.data.get("stock_quantity")
        if raw is None:
            raw = request.data.get("stockQuantity")
        parsed = _to_int(raw)
        if parsed is None or parsed < 0:
            return Response({"message": "stock_quantity must be zero or greater."}, status=status.HTTP_400_BAD_REQUEST)
        item.stock_quantity = parsed

    if "sold_out_threshold" in request.data or "soldOutThreshold" in request.data:
        raw = request.data.get("sold_out_threshold")
        if raw is None:
            raw = request.data.get("soldOutThreshold")
        parsed = _to_int(raw)
        if parsed is None or parsed < 0:
            return Response({"message": "sold_out_threshold must be zero or greater."}, status=status.HTTP_400_BAD_REQUEST)
        item.sold_out_threshold = parsed

    _sync_food_item_availability(item)
    item.save()
    return Response({"item": _serialize_food_item(item, request)}, status=status.HTTP_200_OK)


@api_view(["GET"])
def combos(request: Any):
    """Return available combo offers for a vendor/cinema."""
    vendor_id = request.query_params.get("vendor_id") or request.query_params.get("vendorId")
    hall = (request.query_params.get("hall") or "").strip()

    queryset = Combo.objects.filter(is_available=True)
    if vendor_id:
        queryset = queryset.filter(vendor_id=vendor_id)
    if hall:
        queryset = queryset.filter(
            Q(hall__iexact=hall) | Q(hall__isnull=True) | Q(hall__exact="")
        )

    payload = [_serialize_combo(combo) for combo in queryset.order_by("name")]
    return Response({"combos": payload}, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
@vendor_required
def vendor_combos(request: Any):
    """List or create vendor combo offers."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        combo_list = Combo.objects.filter(vendor=vendor).order_by("-id")
        return Response({"combos": [_serialize_combo(combo) for combo in combo_list]}, status=status.HTTP_200_OK)

    name = str(request.data.get("name") or "").strip()
    description = str(request.data.get("description") or "").strip() or None
    hall = str(request.data.get("hall") or "").strip() or None
    combo_price = _to_decimal(request.data.get("combo_price") or request.data.get("comboPrice"))
    items = request.data.get("items") if isinstance(request.data.get("items"), list) else []
    is_available_raw = request.data.get("is_available")
    if is_available_raw is None:
        is_available_raw = request.data.get("isAvailable")
    is_available = str(is_available_raw).lower() not in {"0", "false", "no"}

    if not name:
        return Response({"message": "name is required."}, status=status.HTTP_400_BAD_REQUEST)
    if combo_price is None or combo_price <= 0:
        return Response({"message": "combo_price must be a positive number."}, status=status.HTTP_400_BAD_REQUEST)
    if not items:
        return Response({"message": "items are required for combo."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        combo = Combo.objects.create(
            vendor=vendor,
            name=name,
            description=description,
            hall=hall,
            combo_price=combo_price,
            is_available=is_available,
        )
        for line in items:
            if not isinstance(line, dict):
                continue
            food_item_id = line.get("food_item_id") or line.get("foodItemId")
            quantity = int(line.get("quantity") or 1)
            food_item = FoodItem.objects.filter(pk=food_item_id, vendor=vendor).first()
            if not food_item:
                transaction.set_rollback(True)
                return Response(
                    {"message": f"Invalid food item in combo: {food_item_id}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if quantity < 1:
                transaction.set_rollback(True)
                return Response({"message": "quantity must be >= 1."}, status=status.HTTP_400_BAD_REQUEST)
            ComboItem.objects.create(combo=combo, food_item=food_item, quantity=quantity)

    return Response({"combo": _serialize_combo(combo)}, status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@vendor_required
def vendor_combo_detail(request: Any, combo_id: int):
    """Update or delete vendor combo offers."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    combo = Combo.objects.filter(pk=combo_id, vendor=vendor).first()
    if not combo:
        return Response({"message": "Combo not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        combo.delete()
        return Response({"message": "Combo deleted."}, status=status.HTTP_200_OK)

    if "name" in request.data:
        next_name = str(request.data.get("name") or "").strip()
        if not next_name:
            return Response({"message": "name cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        combo.name = next_name

    if "description" in request.data:
        combo.description = str(request.data.get("description") or "").strip() or None
    if "hall" in request.data:
        combo.hall = str(request.data.get("hall") or "").strip() or None
    if "combo_price" in request.data or "comboPrice" in request.data:
        next_price = _to_decimal(request.data.get("combo_price") or request.data.get("comboPrice"))
        if next_price is None or next_price <= 0:
            return Response({"message": "combo_price must be a positive number."}, status=status.HTTP_400_BAD_REQUEST)
        combo.combo_price = next_price

    if "is_available" in request.data or "isAvailable" in request.data:
        raw = request.data.get("is_available")
        if raw is None:
            raw = request.data.get("isAvailable")
        combo.is_available = str(raw).lower() not in {"0", "false", "no"}

    if "items" in request.data:
        items = request.data.get("items") if isinstance(request.data.get("items"), list) else []
        if not items:
            return Response({"message": "items cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            ComboItem.objects.filter(combo=combo).delete()
            for line in items:
                if not isinstance(line, dict):
                    continue
                food_item_id = line.get("food_item_id") or line.get("foodItemId")
                quantity = int(line.get("quantity") or 1)
                food_item = FoodItem.objects.filter(pk=food_item_id, vendor=vendor).first()
                if not food_item:
                    transaction.set_rollback(True)
                    return Response(
                        {"message": f"Invalid food item in combo: {food_item_id}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if quantity < 1:
                    transaction.set_rollback(True)
                    return Response({"message": "quantity must be >= 1."}, status=status.HTTP_400_BAD_REQUEST)
                ComboItem.objects.create(combo=combo, food_item=food_item, quantity=quantity)

    combo.save()
    return Response({"combo": _serialize_combo(combo)}, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
def booking_food_orders(request: Any):
    """Create or list customer food orders linked to ticket bookings."""
    if not is_authenticated(request):
        return Response({"message": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

    customer = resolve_customer(request)
    if not customer:
        return Response({"message": "Customer access required"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        booking_id = request.query_params.get("booking_id") or request.query_params.get("bookingId")
        queryset = Order.objects.filter(user=customer).select_related("booking", "vendor")
        if booking_id:
            queryset = queryset.filter(booking_id=booking_id)
        payload = [_serialize_order(order) for order in queryset.order_by("-id")]
        return Response({"orders": payload}, status=status.HTTP_200_OK)

    booking_id = request.data.get("booking_id") or request.data.get("bookingId")
    items = request.data.get("items") if isinstance(request.data.get("items"), list) else []
    if not booking_id:
        return Response({"message": "booking_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not items:
        return Response({"message": "items are required."}, status=status.HTTP_400_BAD_REQUEST)

    booking = Booking.objects.select_related("showtime__screen__vendor").filter(pk=booking_id, user=customer).first()
    if not booking:
        return Response({"message": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

    vendor = booking.showtime.screen.vendor
    booking_hall = str(booking.showtime.screen.screen_number or "").strip()

    total_amount = Decimal("0")
    order_items_payload: list[dict[str, Any]] = []

    with transaction.atomic():
        order = Order.objects.create(booking=booking, user=customer, vendor=vendor)

        for line in items:
            if not isinstance(line, dict):
                continue

            quantity = int(line.get("quantity") or 1)
            if quantity < 1:
                transaction.set_rollback(True)
                return Response({"message": "quantity must be >= 1."}, status=status.HTTP_400_BAD_REQUEST)

            food_item_id = line.get("food_item_id") or line.get("foodItemId")
            combo_id = line.get("combo_id") or line.get("comboId")

            if food_item_id and combo_id:
                transaction.set_rollback(True)
                return Response(
                    {"message": "Choose either food_item_id or combo_id per line."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if food_item_id:
                food_item = FoodItem.objects.select_for_update().filter(
                    pk=food_item_id,
                    vendor=vendor,
                    is_available=True,
                ).first()
                if not food_item:
                    transaction.set_rollback(True)
                    return Response(
                        {"message": f"Food item not available: {food_item_id}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if food_item.hall and booking_hall and str(food_item.hall).strip().lower() != booking_hall.lower():
                    transaction.set_rollback(True)
                    return Response(
                        {"message": f"Food item {food_item.item_name} is not available for this hall."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                unit_price = Decimal(food_item.price)
                line_total = unit_price * quantity

                if food_item.track_inventory:
                    current_stock = int(food_item.stock_quantity or 0)
                    if quantity > current_stock:
                        transaction.set_rollback(True)
                        return Response(
                            {
                                "message": f"Insufficient stock for {food_item.item_name}. Available: {current_stock}",
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    food_item.stock_quantity = current_stock - quantity
                    _sync_food_item_availability(food_item)
                    food_item.save(update_fields=["stock_quantity", "is_available", "sold_out_at"])

                order_item = OrderItem.objects.create(
                    order=order,
                    food_item=food_item,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=line_total,
                )
                BookingFoodItem.objects.update_or_create(
                    booking=booking,
                    food_item=food_item,
                    defaults={
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "total_price": line_total,
                    },
                )
                total_amount += line_total
                order_items_payload.append(
                    {
                        "id": order_item.id,
                        "type": "food_item",
                        "foodItemId": food_item.id,
                        "name": food_item.item_name,
                        "quantity": quantity,
                        "unitPrice": float(unit_price),
                        "totalPrice": float(line_total),
                    }
                )
                continue

            if combo_id:
                combo = Combo.objects.filter(pk=combo_id, vendor=vendor, is_available=True).first()
                if not combo:
                    transaction.set_rollback(True)
                    return Response(
                        {"message": f"Combo not available: {combo_id}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if combo.hall and booking_hall and str(combo.hall).strip().lower() != booking_hall.lower():
                    transaction.set_rollback(True)
                    return Response(
                        {"message": f"Combo {combo.name} is not available for this hall."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                combo_components = list(
                    ComboItem.objects.select_related("food_item")
                    .select_for_update()
                    .filter(combo=combo)
                )
                for component in combo_components:
                    food_item = component.food_item
                    if not food_item:
                        continue
                    if not food_item.is_available:
                        transaction.set_rollback(True)
                        return Response(
                            {"message": f"Combo item unavailable: {component.food_item_id}"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if not food_item.track_inventory:
                        continue

                    required = int(component.quantity or 1) * quantity
                    current_stock = int(food_item.stock_quantity or 0)
                    if required > current_stock:
                        transaction.set_rollback(True)
                        return Response(
                            {
                                "message": f"Insufficient stock for combo component {food_item.item_name}. Available: {current_stock}",
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                # Deduct combo component stock after all checks pass.
                for component in combo_components:
                    food_item = component.food_item
                    if not food_item or not food_item.track_inventory:
                        continue
                    required = int(component.quantity or 1) * quantity
                    food_item.stock_quantity = int(food_item.stock_quantity or 0) - required
                    _sync_food_item_availability(food_item)
                    food_item.save(update_fields=["stock_quantity", "is_available", "sold_out_at"])

                unit_price = Decimal(combo.combo_price)
                line_total = unit_price * quantity
                order_item = OrderItem.objects.create(
                    order=order,
                    combo=combo,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=line_total,
                )
                total_amount += line_total
                order_items_payload.append(
                    {
                        "id": order_item.id,
                        "type": "combo",
                        "comboId": combo.id,
                        "name": combo.name,
                        "quantity": quantity,
                        "unitPrice": float(unit_price),
                        "totalPrice": float(line_total),
                    }
                )
                continue

            transaction.set_rollback(True)
            return Response(
                {"message": "Each item line requires food_item_id or combo_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.total_amount = total_amount
        order.status = Order.STATUS_CONFIRMED
        order.save(update_fields=["total_amount", "status", "updated_at"])

    return Response(
        {
            "message": "Food order created.",
            "order": {
                "id": order.id,
                "bookingId": booking.id,
                "totalAmount": float(order.total_amount),
                "status": order.status,
                "items": order_items_payload,
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def booking_food_order_detail(request: Any, order_id: int):
    """Return one customer food order linked with booking."""
    if not is_authenticated(request):
        return Response({"message": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

    customer = resolve_customer(request)
    if not customer:
        return Response({"message": "Customer access required"}, status=status.HTTP_403_FORBIDDEN)

    order = Order.objects.filter(pk=order_id, user=customer).first()
    if not order:
        return Response({"message": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response({"order": _serialize_order(order)}, status=status.HTTP_200_OK)
