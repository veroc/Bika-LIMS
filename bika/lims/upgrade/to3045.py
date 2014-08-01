from Acquisition import aq_inner
from Acquisition import aq_parent
from Products.CMFCore.utils import getToolByName


def upgrade(tool):
    """ Fix workflow variable review_history permission guard.
    """

    wf_ids = [
        'bika_analysis_workflow',
        'bika_batch_workflow',
        'bika_cancellation_workflow',
        'bika_duplicateanalysis_workflow',
        'bika_inactive_workflow',
        'bika_publication_workflow',
        'bika_referenceanalysis_workflow',
        'bika_referencesample_workflow',
        'bika_reject_analysis_workflow',
        'bika_sample_workflow',
        'bika_worksheet_workflow',
        'bika_worksheetanalysis_workflow',
    ]
    portal = aq_parent(aq_inner(tool))
    workflow = getToolByName(portal, 'portal_workflow')
    for wf_id in wf_ids:
        wf = workflow.getWorkflowById(wf_id)
        rhdef = wf.variables['review_history']
        rhdef.info_guard = None

    return True
