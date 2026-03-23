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
    class Status(models.TextChoices):
        PENDING  = "Pending",  "Pending"
        ACTIVE   = "Active",   "Active"
        ARCHIVED = "Archived", "Archived"

    name = models.CharField(max_length=200)
    date = models.DateTimeField()
    total_spend = models.DecimalField(max_digits=10, decimal_places=2)
    group = models.ForeignKey(Group, related_name='events', on_delete=models.CASCADE)
    members = models.ManyToManyField(User, related_name='events_joined', blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.group.name})"

    def calculate_share(self):
        members_count = self.group.members.count()
        return 0 if members_count == 0 else self.total_spend / members_count

    def check_status(self, save=True):
        if self.status == self.Status.ARCHIVED:
            return self.status
        share = self.calculate_share()
        for member in self.group.members.all():
            if member.profile.max_spend < share:
                self.status = self.Status.PENDING
                if save:
                    self.save(update_fields=["status"])
                return self.status
        self.status = self.Status.ACTIVE
        if save:
            self.save(update_fields=["status"])
        return self.status

    def archive(self, save=True):
        self.status = self.Status.ARCHIVED
        self.archived_at = timezone.now()
        if save:
            self.save(update_fields=["status", "archived_at"])