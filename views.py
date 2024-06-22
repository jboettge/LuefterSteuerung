from .forms import SpecialModeForm

def set_special_mode(request):
    if request.method == 'POST':
        form = SpecialModeForm(request.POST)
        if form.is_valid():
            special_mode = form.cleaned_data['special_mode']
            # Here you can set the special mode
            # set_special_mode(special_mode)
    else:
        form = SpecialModeForm()

    return render(request, 'set_special_mode.html', {'form': form})