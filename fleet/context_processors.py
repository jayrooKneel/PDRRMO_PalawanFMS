from .models import AccountSecurityProfile


def account_security_prompt(request):
    if not request.user.is_authenticated:
        return {'security_setup_required': False}

    profile = AccountSecurityProfile.objects.filter(user_id=request.user.pk).values(
        'security_question',
        'security_answer_hash',
    ).first()
    return {
        'security_setup_required': not profile
        or not profile['security_question']
        or not profile['security_answer_hash'],
    }
