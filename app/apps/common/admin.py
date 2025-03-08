from django.contrib import admin


class SharedObjectModelAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        # Use the all_objects manager to show all transactions, including deleted ones
        return self.model.all_objects.all()
