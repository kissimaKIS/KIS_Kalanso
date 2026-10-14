from django.urls import path
from .views import document_list, document_create, document_delete, document_students
urlpatterns=[path("documents/",document_list,name="document_list"),path("documents/add/",document_create,name="document_create"),path("documents/<int:pk>/delete/",document_delete,name="document_delete"),path("documents/classes/<int:classe_id>/students/",document_students,name="document_students")]
