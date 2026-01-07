document.addEventListener('DOMContentLoaded', function() {
    const indicators = [
        { value: 'SMA', label: 'Simple Moving Average' },
        { value: 'EMA', label: 'Exponential Moving Average' },
        { value: 'RSI', label: 'Relative Strength Index' },
        { value: 'MACD', label: 'Moving Average Convergence Divergence' },
        { value: 'BB', label: 'Bollinger Bands' }
    ];

    const operators = [
        { value: 'crosses_above', label: 'Crosses Above' },
        { value: 'crosses_below', label: 'Crosses Below' },
        { value: 'greater_than', label: 'Greater Than' },
        { value: 'less_than', label: 'Less Than' }
    ];

    let conditionIndex = document.querySelectorAll('.condition-row').length;

    function createConditionElement(type) {
        conditionIndex++;
        const conditionDiv = document.createElement('div');
        conditionDiv.classList.add('row', 'mb-3', 'align-items-center', 'condition-row');
        conditionDiv.setAttribute('data-index', conditionIndex);

        conditionDiv.innerHTML = `
            <div class="col-md-3">
                <select class="form-select" name="${type}_indicator_${conditionIndex}" required>
                    <option value="">Select Indicator</option>
                    ${indicators.map(i => `<option value="${i.value}">${i.label}</option>`).join('')}
                </select>
            </div>
            <div class="col-md-2">
                <input type="text" class="form-control" name="${type}_indicator_param1_${conditionIndex}" placeholder="Param 1">
            </div>
            <div class="col-md-3">
                <select class="form-select" name="${type}_operator_${conditionIndex}" required>
                    <option value="">Select Operator</option>
                    ${operators.map(o => `<option value="${o.value}">${o.label}</option>`).join('')}
                </select>
            </div>
            <div class="col-md-3">
                <input type="text" class="form-control" name="${type}_value_${conditionIndex}" placeholder="Value/Indicator" required>
            </div>
            <div class="col-md-1">
                <button type="button" class="btn btn-danger btn-sm remove-condition">X</button>
            </div>
        `;
        return conditionDiv;
    }

    document.getElementById('add-entry-condition').addEventListener('click', () => {
        const container = document.getElementById('entry-conditions');
        container.appendChild(createConditionElement('entry'));
    });

    document.getElementById('add-exit-condition').addEventListener('click', () => {
        const container = document.getElementById('exit-conditions');
        container.appendChild(createConditionElement('exit'));
    });

    document.addEventListener('click', function(e) {
        if (e.target && e.target.classList.contains('remove-condition')) {
            e.target.closest('.condition-row').remove();
        }
    });
});
