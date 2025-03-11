from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import PIDLoop, BumpTest

@receiver(post_save, sender=PIDLoop)
def update_bump_tests_on_pid_type_change(sender, instance, **kwargs):
    """Update all related BumpTests when PIDLoop type changes."""
    for bump_test in BumpTest.objects.filter(trend_chart__pid_loop=instance):
        bump_test.update_t_notes()
        bump_test.save()
