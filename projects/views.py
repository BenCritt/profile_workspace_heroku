from django.shortcuts import render, redirect
from django.urls import reverse
from .forms import ReviewForm
import os
import qrcode
from django.http import HttpResponse

# from django.http import HttpResponse


def home(request):
    return render(request, "projects/home.html")


def resume(request):
    return render(request, "projects/resume.html")


def qr_code_generator(request):
    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data["qr_text"]
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            home_dir = os.path.expanduser("~")
            save_dir = os.path.join(home_dir, "Downloads")
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            filename = "qrcode.png"
            full_path = os.path.join(save_dir, filename)
            img.save(full_path)

            with open(full_path, "rb") as f:
                response = HttpResponse(f.read(), content_type="image/png")
                response["Content-Disposition"] = 'attachment; filename="qrcode.png"'
                return response
            print(
                "The QR code was successfully created and downloaded to the default downloads folder."
            )
            """
            return render(
                request, "projects/qr_code_generator.html", context={"form": form}
            )
    else:
        form = ReviewForm
    return render(request, "projects/qr_code_generator.html", context={"form": form})


def contact(request):
    return render(request, "projects/contact.html")


"""
def thank_you(request):
    return render(request, "projects/qr_code_generator.html")
"""
