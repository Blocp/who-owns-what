import csv
import logging
from typing import Dict, Any, List
from pathlib import Path
from django.http import HttpResponse, JsonResponse, Http404

from .dbutil import call_db_func, exec_db_query
from . import csvutil, apiutil
from .apiutil import api, get_validated_form_data
from .forms import PaddedBBLForm, SeparatedBBLForm


MY_DIR = Path(__file__).parent.resolve()

SQL_DIR = MY_DIR / 'sql'

logger = logging.getLogger(__name__)


def log_unsupported_request_args(request):
    '''
    Some original API endpoints sometimes got 'houseNumber', 'street',
    'borough' query args, in which case it would look up the BBL. This
    new implementation of the API doesn't currently support them but
    we do want to log anytime we happen to get requests for them, to
    diagnose whether we need to support them.
    '''

    unsupported_args = ['houseNumber', 'street', 'borough']
    if set(request.GET.keys()).issuperset(unsupported_args):
        logger.error(
            f'Request contains unsupported arguments: {", ".join(unsupported_args)}')


@api
def address_query(request):
    log_unsupported_request_args(request)
    args = get_validated_form_data(SeparatedBBLForm, request.GET)
    bbl = args['borough'] + args['block'] + args['lot']

    addrs = call_db_func('get_assoc_addrs_from_bbl', [bbl])

    return JsonResponse({
        "geosearch": {
            "geosupportReturnCode": "00",
            "bbl": bbl,
        },
        "addrs": addrs,
    })


@api
def address_dap_aggregate(request):
    '''
    This endpoint is used specifically by the DAP Portal:

        https://portal.displacementalert.org/

    We should make sure we don't change its behavior without
    notifying them.
    '''

    return address_aggregate(request)


def get_request_bbl(request) -> str:
    return get_validated_form_data(PaddedBBLForm, request.GET)['bbl']


@api
def address_aggregate(request):
    bbl = get_request_bbl(request)
    result = call_db_func('get_agg_info_from_bbl', [bbl])
    return JsonResponse({ 'result': result })


@api
def address_buildinginfo(request):
    bbl = get_request_bbl(request)
    result = exec_db_query(SQL_DIR / 'address_buildinginfo.sql', { 'bbl': bbl })
    return JsonResponse({ 'result': result })


@api
def address_indicatorhistory(request):
    bbl = get_request_bbl(request)
    result = exec_db_query(SQL_DIR / 'address_indicatorhistory.sql', { 'bbl': bbl })
    return JsonResponse({ 'result': result })


@api
def address_export(request):
    log_unsupported_request_args(request)
    bbl = get_request_bbl(request)
    addrs = call_db_func('get_assoc_addrs_from_bbl', [bbl])

    if not addrs:
        return HttpResponse(status=404)

    first_row = addrs[0]

    for addr in addrs:
        addr['ownernames'] = csvutil.stringify_owners(addr['ownernames'])
        csvutil.stringify_lists(addr)

    # https://docs.djangoproject.com/en/3.0/howto/outputting-csv/
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="wow-addresses-{bbl}.csv"'

    writer = csv.DictWriter(response, list(first_row.keys()))
    writer.writeheader()
    writer.writerows(addrs)

    return response


def server_error(request):
    if apiutil.is_api_request(request):
        return apiutil.apply_cors_policy(request, JsonResponse(
            {'error': 'An internal server error occurred.'},
            status=500,
        ))

    from django.views import defaults
    return defaults.server_error(request)