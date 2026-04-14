import re
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


# ---------------------------------------------------------------------------
# USER
# ---------------------------------------------------------------------------

class User(AbstractUser):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    role = models.CharField(
        max_length=10,
        choices=[('student', 'Student'), ('admin', 'Admin')],
        default='student',
    )
    email_notifications = models.BooleanField(default=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    @property
    def is_registrar(self):
        return self.role == 'admin'

    @property
    def is_student(self):
        return self.role == 'student'

    def __str__(self):
        return self.email


# ---------------------------------------------------------------------------
# DOCUMENT TYPE
# ---------------------------------------------------------------------------

class DocumentType(models.Model):
    name = models.CharField(max_length=120, unique=True)
    fee = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# REQUEST
# ---------------------------------------------------------------------------

STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('under_review', 'Under Review'),
    ('processing', 'Processing'),
    ('for_revision', 'For Revision'),
    ('ready_for_release', 'Ready for Release'),
    ('completed', 'Completed'),
    ('rejected', 'Rejected'),
]

VALID_TRANSITIONS = {
    'pending': ['under_review', 'rejected'],
    'under_review': ['processing', 'for_revision', 'rejected'],
    'processing': ['ready_for_release', 'for_revision', 'rejected'],
    'for_revision': ['under_review', 'rejected'],
    'ready_for_release': ['completed'],
    'completed': [],
    'rejected': [],
}

YEAR_LEVEL_CHOICES = [
    ('1st Year', '1st Year'),
    ('2nd Year', '2nd Year'),
    ('3rd Year', '3rd Year'),
    ('4th Year', '4th Year'),
    ('5th Year', '5th Year'),
    ('Graduate', 'Graduate'),
    ('Alumni', 'Alumni'),
]


def generate_ref_number():
    from django.utils import timezone
    year = timezone.now().year
    prefix = f"{year}-"
    last = (
        Request.objects.filter(ref_number__startswith=prefix)
        .order_by('-ref_number')
        .values_list('ref_number', flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.split('-')[1]) + 1
        except (IndexError, ValueError):
            seq = 1
    else:
        seq = 1
    return f"{year}-{seq:05d}"


class Request(models.Model):
    ref_number = models.CharField(max_length=20, unique=True, editable=False)
    student = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='requests',
        limit_choices_to={'role': 'student'},
    )
    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        related_name='requests',
    )
    first_name = models.CharField(max_length=80)
    middle_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80)
    student_number = models.CharField(
        max_length=30,
        validators=[RegexValidator(r'^[A-Za-z0-9\-]+$', 'Only letters, digits, and hyphens are allowed.')],
    )
    course = models.CharField(max_length=120)
    year_level = models.CharField(max_length=20, choices=YEAR_LEVEL_CHOICES)
    school_year = models.CharField(
        max_length=9,
        validators=[RegexValidator(r'^\d{4}-\d{4}$', 'Format: YYYY-YYYY')],
        help_text='Format: YYYY-YYYY',
    )
    purpose = models.TextField(max_length=500)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
    )
    fee_amount = models.DecimalField(max_digits=8, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['student', 'status']),
            models.Index(fields=['ref_number']),
        ]

    def save(self, *args, **kwargs):
        if not self.ref_number:
            self.ref_number = generate_ref_number()
        if not self.fee_amount:
            self.fee_amount = self.document_type.fee
        super().save(*args, **kwargs)

    def can_transition_to(self, new_status):
        return new_status in VALID_TRANSITIONS.get(self.status, [])

    @property
    def full_name(self):
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return ' '.join(parts)

    @property
    def can_download(self):
        return self.status in ('ready_for_release', 'completed')

    def __str__(self):
        return f"{self.ref_number} — {self.full_name}"


# ---------------------------------------------------------------------------
# STATUS LOG
# ---------------------------------------------------------------------------

class StatusLog(models.Model):
    request = models.ForeignKey(
        Request,
        on_delete=models.CASCADE,
        related_name='status_logs',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='status_changes',
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.request.ref_number} → {self.status}"


# ---------------------------------------------------------------------------
# PAYMENT
# ---------------------------------------------------------------------------

class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('gcash', 'GCash'),
        ('bank_transfer', 'Bank Transfer'),
        ('over_the_counter', 'Over-the-counter'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    request = models.ForeignKey(
        Request,
        on_delete=models.CASCADE,
        related_name='payments',
    )
    method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    receipt = models.ImageField(upload_to='receipts/%Y/%m/')
    status = models.CharField(
        max_length=10,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending',
    )
    note = models.TextField(blank=True)
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='submitted_payments',
    )
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_payments',
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment {self.id} — {self.request.ref_number} ({self.status})"


# ---------------------------------------------------------------------------
# RELEASED DOCUMENT
# ---------------------------------------------------------------------------

class ReleasedDocument(models.Model):
    request = models.ForeignKey(
        Request,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    file = models.FileField(upload_to='documents/%Y/%m/')
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_documents',
    )
    is_latest = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.is_latest:
            ReleasedDocument.objects.filter(
                request=self.request, is_latest=True
            ).update(is_latest=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Doc for {self.request.ref_number} (latest={self.is_latest})"
