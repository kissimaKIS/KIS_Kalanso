def get_exam_info(classe):
    level = classe.education_level
    return {
        "exam": level.exam_name or None,
        "is_exam": level.is_exam_level,
        "allows_free_candidate": level.allows_free_candidate,
    }
