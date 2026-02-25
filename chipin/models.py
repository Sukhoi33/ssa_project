from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
from decimal import Decimal


# helper for invite expiration used previously in migrations
def default_invite_expiry():
    # default to one week from now
    return timezone.now() + timezone.timedelta(days=7)


class Group(models.Model):
    name = models.CharField(max_length=100)
    admin = models.ForeignKey(User, related_name='admin_groups', on_delete=models.CASCADE)
    members = models.ManyToManyField(User, related_name='group_memberships', blank=True)
    invited_users = models.ManyToManyField(User, related_name='pending_invitations', blank=True)

    def __str__(self):
        return self.name


class Invite(models.Model):
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_invite_expiry)
    group = models.ForeignKey(Group, related_name='invites', on_delete=models.CASCADE)
    invited_by = models.ForeignKey(User, related_name='sent_invites', on_delete=models.CASCADE)
    invited_user = models.ForeignKey(User, related_name='group_invites', on_delete=models.CASCADE)

    def __str__(self):
        return f"Invite to {self.invited_user.username} for {self.group.name} (accepted={self.accepted})"

    def accept_url(self):
        # build a url that can be used to accept this invite
        # token is included for basic validation
        from django.urls import reverse
        return f"{reverse('chipin:accept_invite', args=[self.group.id])}?user_id={self.invited_user.id}&token={self.token}"


class GroupJoinRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, related_name='join_requests', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} requests to join {self.group.name}"  


class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # User who posted the comment
    group = models.ForeignKey(Group, related_name='comments', on_delete=models.CASCADE)  # Group associated with the comment
    content = models.TextField()  # The comment content
    created_at = models.DateTimeField(auto_now_add=True)  # Timestamp when the comment was posted
    updated_at = models.DateTimeField(auto_now=True)  # Timestamp for the latest update

    def __str__(self):
        return f"{self.user.username}: {self.content[:20]}..."  # Show only first 20 chars for preview


class Event(models.Model):
    STATUS_PENDING = 'Pending'
    STATUS_ACTIVE = 'Active'
    STATUS_COMPLETED = 'Completed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_COMPLETED, 'Completed'),
    ]

    name = models.CharField(max_length=200)
    date = models.DateTimeField()
    total_spend = models.DecimalField(max_digits=10, decimal_places=2)
    group = models.ForeignKey(Group, related_name='events', on_delete=models.CASCADE)
    members = models.ManyToManyField(User, related_name='events_joined', blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.group.name})"

    def calculate_share(self):
        """Return the per-member share as Decimal. If there are no members yet,
        divide by the number of group members to give an expected share.
        """
        try:
            total = Decimal(self.total_spend)
        except Exception:
            total = Decimal('0.00')

        num = self.members.count()
        if num == 0:
            num = self.group.members.count() or 1
        return (total / Decimal(num)).quantize(Decimal('0.01'))

    def check_status(self):
        """Set status to Active if all current group members can afford the share."""
        share = self.calculate_share()
        for member in self.group.members.all():
            try:
                max_spend = member.profile.max_spend
            except Exception:
                max_spend = Decimal('0.00')
            if max_spend < share:
                self.status = self.STATUS_PENDING
                return
        self.status = self.STATUS_ACTIVE