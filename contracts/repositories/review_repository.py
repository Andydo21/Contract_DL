from contracts.models import Review


class ReviewRepository:
    @staticmethod
    def create_review(analysis, user, comment, final_risk_level):
        return Review.objects.create(
            analysis=analysis,
            user=user,
            note=comment,
            decision=final_risk_level
        )
