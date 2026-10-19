try { var t = localStorage.getItem("theme"); if (t) document.documentElement.className = t; } catch (e) { /* storage unavailable */ }
