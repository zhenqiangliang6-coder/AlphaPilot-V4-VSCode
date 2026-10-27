class VotingSystem:
    def get_candidate_votes(self):
        return 5

def test_get_vote_count():
    assert get_vote_count() == 5