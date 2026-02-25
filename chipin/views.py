from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.utils import timezone
from django.conf import settings
from .models import Group, Comment, Invite, GroupJoinRequest, Event
from .forms import GroupCreationForm, CommentForm
from django.urls import reverse

@login_required
def home(request):
    user = request.user
    pending_invitations = user.pending_invitations.all() # Get pending group invitations for the current user
    user_groups = user.group_memberships.all()  # Get groups the user is a member of
    user_join_requests = GroupJoinRequest.objects.filter(user=user)  # Get join requests sent by the user
    available_groups = Group.objects.exclude(members=user).exclude(join_requests__user=user) # Get groups the user is not a member of and the user has not requested to join
    context = {
        'pending_invitations': pending_invitations,
        'user_groups': user_groups,
        'user_join_requests': user_join_requests,
        'available_groups': available_groups
    }
    return render(request, 'chipin/home.html', context)

@login_required
def create_group(request):
    if request.method == 'POST':
        form = GroupCreationForm(request.POST, user=request.user)
        if form.is_valid():
            group = form.save()
            messages.success(request, f'Group "{group.name}" created successfully!')
            return redirect('chipin:group_detail', group_id=group.id)
    else:
        form = GroupCreationForm(user=request.user)
    return render(request, 'chipin/create_group.html', {'form': form})


@login_required
def delete_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user == group.admin:
        group.delete()
        messages.success(request, f'Group "{group.name}" has been deleted.')
    else:
        messages.error(request, "You do not have permission to delete this group.")
    return redirect('chipin:home')

@login_required
def invite_users(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    users_not_in_group = User.objects.exclude(id__in=group.members.values_list('id', flat=True))
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        invited_user = get_object_or_404(User, id=user_id)      
        if invited_user in group.invited_users.all():
            messages.info(request, f'{invited_user.username} has already been invited.')
        else:
            group.invited_users.add(invited_user)
            messages.success(request, f'Invitation sent to {invited_user.username}.')
        return redirect('chipin:group_detail', group_id=group.id)  
    return render(request, 'chipin/invite_users.html', {
        'group': group,
        'users_not_in_group': users_not_in_group
    })

@login_required
def web3forms_invite(request, group_id, invite_id):
    invite = get_object_or_404(Invite, id=invite_id, group_id=group_id)
    accept_link = invite.accept_url()
    WEB3FORMS_ACCESS_KEY = getattr(settings, "WEB3FORMS_ACCESS_KEY", "")

    thank_you_url = request.build_absolute_uri(
            reverse("chipin:invite_sent") + f"?group={invite.group.id}&invite={invite.id}"
        )

    return render(
        request,
        "chipin/web3forms_invite.html",
        {
            "group": invite.group,
            "invite": invite,
            "accept_link": accept_link,
            "WEB3FORMS_ACCESS_KEY": WEB3FORMS_ACCESS_KEY,
            "redirect_url": thank_you_url,
        },
    )

@login_required
def accept_invite(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    user_id = request.GET.get('user_id')
    if user_id:
        invited_user = get_object_or_404(User, id=user_id)
        if invited_user in group.members.all():
            messages.info(request, f'{invited_user.username} is already a member of the group "{group.name}".')
        elif invited_user in group.invited_users.all():
            group.members.add(invited_user)
            group.invited_users.remove(invited_user)  # Remove from invited list
            messages.success(request, f'{invited_user.username} has successfully joined the group "{group.name}".')
        else:
            messages.error(request, "You are not invited to join this group.")
    else:
        messages.error(request, "Invalid invitation link.")  
    return redirect('chipin:group_detail', group_id=group.id)

def _auto_login_as_invitee(request, invite):
    user = invite.invited_user
    backend = None
    try:
        backend = settings.AUTHENTICATION_BACKENDS[0]
    except Exception:
        backend = "django.contrib.auth.backends.ModelBackend"
    setattr(user, "backend", backend)
    login(request, user)

@login_required
def invite_sent(request):
    group_id = request.GET.get("group")
    invite_id = request.GET.get("invite")
    group = get_object_or_404(Group, id=group_id) if group_id else None
    invite = get_object_or_404(Invite, id=invite_id) if invite_id else None
    return render(
        request,
        "chipin/invite_sent.html",
        {
            "group": group,
            "invite": invite,
        },
    )

@login_required
def request_to_join_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user in group.members.all():
        messages.info(request, "You’re already a member of this group.")
    else:
        existing = GroupJoinRequest.objects.filter(user=request.user, group=group).first()
        if existing:
            messages.info(request, "You have already requested to join this group.")
        else:
            GroupJoinRequest.objects.create(user=request.user, group=group)
            messages.success(request, "Your request to join the group has been submitted.")
    return redirect('chipin:group_detail', group_id=group.id)


@login_required
def vote_on_join_request(request, group_id, request_id, vote):
    group = get_object_or_404(Group, id=group_id)
    join_request = get_object_or_404(GroupJoinRequest, id=request_id, group=group)

    if request.user not in group.members.all():
        messages.error(request, "Only group members may vote on join requests.")
        return redirect('chipin:group_detail', group_id=group.id)

    if vote == 'approve':
        group.members.add(join_request.user)
        join_request.delete()
        messages.success(request, f"{join_request.user.profile.nickname} has been added to the group.")
    else:
        join_request.delete()
        messages.info(request, "Join request rejected.")

    return redirect('chipin:group_detail', group_id=group.id)


@login_required
def delete_join_request(request, request_id):
    jr = get_object_or_404(GroupJoinRequest, id=request_id)
    if jr.user == request.user or request.user == jr.group.admin:
        jr.delete()
        messages.success(request, "Join request removed.")
    else:
        messages.error(request, "You don’t have permission to delete that request.")
    return redirect('chipin:home')


@login_required
def leave_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    if request.user not in group.members.all():
        messages.error(request, "You’re not a member of this group.")
        return redirect("chipin:group_detail", group_id=group.id)

    if request.user == group.admin:
        messages.error(request, "Admins can’t leave their own group. Transfer admin or delete the group.")
        return redirect("chipin:group_detail", group_id=group.id)

    group.members.remove(request.user)
    messages.success(request, f'You left "{group.name}".')
    return redirect("chipin:home")


@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if comment.user == request.user or request.user == comment.group.admin:  # Allow author or group admin to delete
        comment.delete()
    return redirect('chipin:group_detail', group_id=comment.group.id)

@login_required
def group_detail(request, group_id, edit_comment_id=None):
    group = get_object_or_404(Group, id=group_id)
    comments = group.comments.all().order_by('-created_at')  # Fetch all comments for the group
    if edit_comment_id: # Fetch the comment to edit, if edit_comment_id is provided
        comment_to_edit = get_object_or_404(Comment, id=edit_comment_id)
        # only the author or group admin can edit
        if comment_to_edit.user != request.user and request.user != group.admin:
            return redirect('chipin:group_detail', group_id=group.id)
    else:
        comment_to_edit = None
    if request.method == 'POST':
        # only members can post or edit comments
        if request.user not in group.members.all():
            messages.error(request, "You must be a member of the group to post comments.")
            return redirect('chipin:group_detail', group_id=group.id)

        if comment_to_edit: # Editing an existing comment
            form = CommentForm(request.POST, instance=comment_to_edit)
        else: # Adding a new comment
            form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.group = group
            comment.save()
            return redirect('chipin:group_detail', group_id=group.id)
    else:
        form = CommentForm(instance=comment_to_edit) if comment_to_edit else CommentForm()
    # include events if present (Event model added)
    events = group.events.all() if hasattr(group, 'events') else []
    # Calculate event share for each event and check user eligibility
    event_share_info = {}
    for event in events:
        try:
            event_share = event.calculate_share()
        except Exception:
            event_share = 0
        try:
            user_eligible = request.user.profile.max_spend >= event_share
        except Exception:
            user_eligible = False
        user_has_joined = request.user in event.members.all() if hasattr(event, 'members') else False
        event_share_info[event] = {
            'share': event_share,
            'eligible': user_eligible,
            'status': getattr(event, 'status', None),
            'joined': user_has_joined
        }
    # Render page with events included
    return render(request, 'chipin/group_detail.html', {
        'group': group,
        'comments': comments,
        'form': form,
        'comment_to_edit': comment_to_edit,
        'events': events,
        'event_share_info': event_share_info,
    })

@login_required
def create_event(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user != group.admin:
        messages.error(request, "Only the group administrator can create events.")
        return redirect('chipin:group_detail', group_id=group.id)
    if request.method == 'POST':
        event_name = request.POST.get('name')
        event_date = request.POST.get('date')
        total_spend = request.POST.get('total_spend')
        event = Event.objects.create(
            name=event_name,
            date=event_date,
            total_spend=total_spend,
            group=group
        )
        messages.success(request, f'Event "{event_name}" created successfully!')
        return redirect('chipin:group_detail', group_id=group.id)
    return render(request, 'chipin/create_event.html', {'group': group})

@login_required
def join_event(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)
    event_share = event.calculate_share()  
    # Check if the user is eligible to join based on their max spend
    if request.user.profile.max_spend < event_share:
        messages.error(request, f"Your max spend of ${request.user.profile.max_spend} is too low to join this event.")
        return redirect('chipin:group_detail', group_id=group.id)
    # Check if the user has already joined the event
    if request.user in event.members.all():
        messages.info(request, "You have already joined this event.")
        return redirect('chipin:group_detail', group_id=group.id)
    # Add the user to the event
    event.members.add(request.user)   
    messages.success(request, f"You have successfully joined the event '{event.name}'.")  
    # Optionally, update the event status if needed
    event.check_status()
    event.save()
    return redirect('chipin:group_detail', group_id=group.id)


@login_required
def update_event_status(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)
    # Ensure that only the group admin can update the event status
    if request.user != group.admin:
        messages.error(request, "Only the group administrator can update the event status.")
        return redirect('chipin:group_detail', group_id=group.id)
    # Calculate the share per member
    event_share = event.calculate_share()
    # Check if all members can afford the event share
    sufficient_funds = True
    for member in group.members.all():
        if member.profile.max_spend < event_share:
            sufficient_funds = False
            break
    # Update the event status based on the members' ability to cover the share
    if sufficient_funds:
        event.status = "Active"
        messages.success(request, f"The event '{event.name}' is now Active. All members can cover the cost.")
    else:
        event.status = "Pending"
        messages.warning(request, f"The event '{event.name}' remains Pending. Some members cannot cover the cost.")
    # Save the updated event status
    event.save()
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
def leave_event(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)
    # Check if the user is part of the event
    if request.user not in event.members.all():
        messages.error(request, "You are not a member of this event.")
        return redirect('chipin:group_detail', group_id=group.id)
    # Remove the user from the event
    event.members.remove(request.user)
    messages.success(request, f"You have successfully left the event '{event.name}'.")
    # Optionally, check if the event status should be updated
    event.check_status()
    event.save()
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
def delete_event(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)
    # Ensure only the group admin can delete the event
    if request.user != group.admin:
        messages.error(request, "Only the group administrator can delete events.")
        return redirect('chipin:group_detail', group_id=group.id)
    # Delete the event
    event.delete()
    messages.success(request, f"The event '{event.name}' has been deleted.")
    return redirect('chipin:group_detail', group_id=group.id)