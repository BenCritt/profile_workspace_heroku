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
            return render(
                request,
                "projects/qr_code_generator.html",
                context={"form": form},
            )
    else:
        form = ReviewForm
    return render(request, "projects/qr_code_generator.html", context={"form": form})


def contact(request):
    return render(request, "projects/contact.html")


from django.shortcuts import render
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from .forms import MonteCarloForm


def monte_carlo_simulator(request):
    if request.method == "POST":
        form = MonteCarloForm(request.POST)
        if form.is_valid():
            # This determines where to save the PDF file that will eventually be created.
            home_dir = os.path.expanduser("~")
            save_dir = os.path.join(home_dir, "Downloads")
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            filename = "probability_graph.pdf"
            full_path = os.path.join(save_dir, filename)

            # This pulls the data from the HTML to prepare for the graph generation.
            sim_quantity = form.cleaned_data["sim_quantity"]
            min_val = form.cleaned_data["min_val"]
            max_val = form.cleaned_data["max_val"]
            target_val = form.cleaned_data["target_val"]

            sim_result = np.random.uniform(min_val, max_val, sim_quantity)
            second_sim_quantity = form.cleaned_data["second_sim_quantity"]
            # Begin second data range, if there is one.
            if form.cleaned_data["second_sim_quantity"] is not None:
                second_min_val = form.cleaned_data["second_min_val"]
                second_max_val = form.cleaned_data["second_max_val"]
                second_target_val = form.cleaned_data["second_target_val"]

                # Generate data for the second range.
                second_sim_result = np.random.uniform(
                    second_min_val, second_max_val, second_sim_quantity
                )

                # Create the visual graph.
                plt.figure()
                plt.hist(sim_result, density=True, edgecolor="white")
                plt.axvline(target_val, color="r")
                if second_target_val != None:
                    plt.hist(
                        second_sim_result, density=True, edgecolor="white", alpha=0.5
                    )
                    plt.axvline(second_target_val, color="b")
                else:
                    plt.hist(
                        second_sim_result, density=True, edgecolor="white", alpha=0.5
                    )
                plt.savefig(full_path, format="pdf")

                with open(full_path, "rb") as f:
                    response = HttpResponse(f.read(), content_type="pdf")
                    response[
                        "Content-Disposition"
                    ] = 'attachment; filename="probability_graph.pdf"'
                    return response

            elif form.cleaned_data["second_sim_quantity"] is None:
                plt.figure()
                plt.hist(sim_result, density=True, edgecolor="white")
                plt.axvline(target_val, color="r")
                plt.savefig(full_path, format="pdf")

                with open(full_path, "rb") as f:
                    response = HttpResponse(f.read(), content_type="pdf")
                    response[
                        "Content-Disposition"
                    ] = 'attachment; filename="probability_graph.pdf"'
                    return response

    else:
        form = MonteCarloForm()

    return render(
        request, "projects/monte_carlo_simulator.html", context={"form": form}
    )
