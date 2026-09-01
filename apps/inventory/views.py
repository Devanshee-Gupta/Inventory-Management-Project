from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView
from rest_framework import viewsets

from apps.accounts.permissions import IsManagerOrReadOnly, ManagerRequiredMixin

from .forms import CategoryForm
from .models import Category
from .serializers import CategorySerializer


# ---- Template views (server-rendered, Bootstrap) ----

class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = "inventory/category_list.html"
    context_object_name = "categories"
    paginate_by = 20


class CategoryCreateView(ManagerRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "inventory/category_form.html"
    success_url = reverse_lazy("category-list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class CategoryUpdateView(ManagerRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "inventory/category_form.html"
    success_url = reverse_lazy("category-list")
    # NOTE: created_by is not in CategoryForm.fields, so it cannot be
    # overwritten through this view even if the form is tampered with.


# ---- DRF API (session-authenticated) ----

class CategoryViewSet(viewsets.ModelViewSet):
    """
    list/retrieve  -> any authenticated user (Manager or Staff)
    create/update  -> Manager only
    delete         -> disabled entirely (no business rule permits deleting
                       a Category once items may reference it)
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsManagerOrReadOnly]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)