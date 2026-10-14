class NumberingService:
    @staticmethod
    def next_receipt_number():
        from administration.models import School, SchoolYear
        from finance.models import Payment

        school = School.objects.filter(is_active=True).first()
        if school is None:
            raise ValueError("Aucun établissement configuré.")

        school_year = SchoolYear.objects.filter(is_active=True, is_closed=False).first()
        if school_year is None:
            raise ValueError("Aucune année scolaire active.")

        prefix = f"{school.code}-{school_year.start_date.year}-"
        # Plus grand numéro déjà attribué (reçus simples et reçus groupés), et non
        # un simple comptage : les lignes d'un reçu groupé portent un suffixe
        # (« -00012/2 ») et ne doivent pas faire sauter la numérotation.
        from finance.models import PaymentBatch
        import re
        pattern = re.compile(re.escape(prefix) + r"(\d+)")
        highest = 0
        # Les reçus annulés restent réservés : leur numéro n'est jamais réattribué.
        from administration.models import CorrectionLog
        for model in (Payment, PaymentBatch, CorrectionLog):
            for number in model.objects.filter(receipt_number__startswith=prefix).values_list("receipt_number", flat=True):
                match = pattern.match(number)
                if match:
                    highest = max(highest, int(match.group(1)))
        return f"{prefix}{highest + 1:05d}"
