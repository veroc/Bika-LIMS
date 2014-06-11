"use strict";

var test = {};

(function($) {

    function setDurationField(form, name, value) {
        var inputs = $('input[name^=' + name + ']', form);
        inputs.filter('[name*=days]').val(value.days);
        inputs.filter('[name*=hours]').val(value.hours);
        inputs.filter('[name*=minutes]').val(value.minutes);
    };

    function setTemplate(form, title) {
        // Construct the JSON API request
        var request_data = {
            portal_type: 'SRTemplate',
            title: title,
            include_fields: [
                'Description',
                'Sampler',
                'SamplingFrequency',
                'Department',
                'DepartmentUID',
                'Instructions',
                'ARTemplates'
            ]
        };
        // Query the JSON API
        window.bika.lims.jsonapi_read(request_data, function(data) {
            // Get the template from the response
            var template = data.objects[0];
            setDurationField(
                form, 'SamplingFrequency', template.SamplingFrequency
            );
            $('#Sampler', form).val(template.Sampler);
            $('#Department', form).val(template.Department);
            $('#Department_uid', form).val(template.Department_uid);
            $('#Instructions', form).val(template.Instructions);
        });
    };

    $(document).ready(function() {
        // Get the SamplingRound edit form
        var form = $('#samplinground-base-edit');
        // Rig the Template field
        $('#Template', form).on('selected', function() {
            setTemplate(form, $(this).val());
        });
    });

}(jQuery));
