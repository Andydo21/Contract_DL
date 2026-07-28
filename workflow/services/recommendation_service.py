class WorkflowRecommendationService:
    """
    Placeholder service for AI-powered workflow recommendation.
    Returns mock data. Will be replaced with real AI inference later.
    """

    @staticmethod
    def recommend(contract_data):
        """
        Generate a mock workflow recommendation based on contract data.
        In the future, this will call an AI model (e.g. HuggingFace)
        to analyze the contract and recommend the optimal approval workflow.

        Args:
            contract_data (dict): Contract metadata and content.

        Returns:
            dict: Mock recommendation payload.
        """
        contract_type = contract_data.get('contract_type', 'general')
        contract_value = contract_data.get('contract_value', 0)
        risk_level = contract_data.get('risk_level', 'MEDIUM')

        # --- Mock logic: vary response based on input ---
        if risk_level == 'HIGH' or (contract_value and float(contract_value) > 500000):
            return {
                'workflow_name': 'Enterprise High-Value Procurement Workflow',
                'confidence': 95,
                'reasoning': [
                    'Contract value exceeds $500,000 threshold',
                    'High risk level requires additional approval layers',
                    'Contains procurement clauses requiring finance review',
                    'Regulatory compliance verification needed',
                ],
                'steps': [
                    'Legal Review',
                    'Compliance Check',
                    'Finance Review',
                    'Manager Approval',
                    'Director Approval',
                    'Contract Signing',
                    'Archive',
                ],
            }

        if contract_type and contract_type.lower() in ('nda', 'non-disclosure'):
            return {
                'workflow_name': 'Standard NDA Approval Workflow',
                'confidence': 92,
                'reasoning': [
                    'Non-disclosure agreement detected',
                    'Standard confidentiality terms identified',
                    'Low complexity — fast-track eligible',
                ],
                'steps': [
                    'Legal Review',
                    'Manager Approval',
                    'Contract Signing',
                    'Archive',
                ],
            }

        # Default mid-range recommendation
        return {
            'workflow_name': 'Enterprise Procurement Workflow',
            'confidence': 88,
            'reasoning': [
                'Contract value is within standard range',
                'Contains procurement clauses',
                'Contains payment schedule',
                'Standard approval path recommended',
            ],
            'steps': [
                'Legal Review',
                'Finance Review',
                'Manager Approval',
                'Director Approval',
                'Contract Signing',
                'Archive',
            ],
        }
