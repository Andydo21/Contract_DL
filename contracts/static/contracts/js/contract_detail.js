document.addEventListener('DOMContentLoaded', () => {
    // 1. Gauge Animation
    const gauge = document.getElementById('gauge-val');
    const gaugeStatus = document.getElementById('gauge-status');
    
    if (gauge) {
        const score = parseFloat(gauge.dataset.score);
        const r = 36;
        const circumference = 2 * Math.PI * r;
        const offset = circumference - (score / 100) * circumference;
        
        // Trigger stroke offset transition
        setTimeout(() => {
            gauge.style.strokeDashoffset = offset;
        }, 100);
        
        // Color the circle and update status text
        if (score >= 80) {
            gauge.style.stroke = '#ef4444';
            gaugeStatus.innerHTML = 'High Risk';
            gaugeStatus.className = 'gauge-status score-high';
        } else if (score >= 50) {
            gauge.style.stroke = '#f97316';
            gaugeStatus.innerHTML = 'Medium Risk';
            gaugeStatus.className = 'gauge-status score-medium';
        } else {
            gauge.style.stroke = '#10b981';
            gaugeStatus.innerHTML = 'Low Risk';
            gaugeStatus.className = 'gauge-status score-low';
        }
    }

    // 2. Expert Review Form Handling
    const reviewForm = document.getElementById('detail-review-form');
    if (reviewForm) {
        reviewForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const analysisId = reviewForm.dataset.analysisId;
            const final_risk_level = reviewForm.final_risk_level.value;
            const comment = reviewForm.comment.value;
            
            try {
                const res = await fetch(`/api/analyses/${analysisId}/review/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ final_risk_level, comment })
                });
                
                const data = await res.json();
                if (data.success) {
                    // Reload the detail page to show approved status
                    window.location.reload();
                } else {
                    alert("Error submitting review: " + (data.error || "Unknown error"));
                }
            } catch (err) {
                console.error(err);
                alert("Failed to submit review request.");
            }
        });
    }
});

// Toggle folding/unfolding of risk findings (Global helper)
window.toggleFinding = function(header) {
    const item = header.parentElement;
    item.classList.toggle('active');
    
    const body = item.querySelector('.finding-body');
    const icon = header.querySelector('i');
    
    if (item.classList.contains('active')) {
        body.style.display = 'flex';
        icon.style.transform = 'rotate(180deg)';
    } else {
        body.style.display = 'none';
        icon.style.transform = 'rotate(0deg)';
    }
};
