from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Group, Comment, GroupJoinRequest


class GroupChatTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='pass')
        self.other = User.objects.create_user(username='bob', password='pass')
        self.group = Group.objects.create(name='test', admin=self.user)
        self.group.members.add(self.user)

    def test_post_comment_as_member(self):
        self.client.login(username='alice', password='pass')
        url = reverse('chipin:group_detail', args=[self.group.id])
        response = self.client.post(url, {'content': 'hello'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.group.comments.count(), 1)
        comment = self.group.comments.first()
        self.assertEqual(comment.content, 'hello')

    def test_non_member_cannot_comment(self):
        self.client.login(username='bob', password='pass')
        url = reverse('chipin:group_detail', args=[self.group.id])
        response = self.client.post(url, {'content': 'hi'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.group.comments.count(), 0)

    def test_join_request_flow(self):
        self.client.login(username='bob', password='pass')
        req_url = reverse('chipin:request_to_join_group', args=[self.group.id])
        resp = self.client.post(req_url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(GroupJoinRequest.objects.filter(user=self.other).count(), 1)
        jr = GroupJoinRequest.objects.get(user=self.other)
        # approve by admin
        self.client.login(username='alice', password='pass')
        vote_url = reverse('chipin:vote_on_join_request', args=[self.group.id, jr.id, 'approve'])
        resp2 = self.client.get(vote_url)
        self.assertEqual(resp2.status_code, 302)
        self.assertTrue(self.other in self.group.members.all())

