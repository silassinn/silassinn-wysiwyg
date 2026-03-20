/* ============================================================
   Ollie Tripp Massage Therapy — main.js
   ============================================================ */

(function () {
  'use strict';

  /* ---- Navbar: transparent → solid on scroll ---- */
  const navbar = document.querySelector('.navbar');
  if (navbar) {
    const heroEl = document.querySelector('.hero');
    function updateNav() {
      if (heroEl) {
        if (window.scrollY > 20) {
          navbar.classList.add('scrolled');
          navbar.classList.remove('transparent');
        } else {
          navbar.classList.remove('scrolled');
          navbar.classList.add('transparent');
        }
      } else {
        navbar.classList.add('scrolled');
        navbar.classList.remove('transparent');
      }
    }
    updateNav();
    window.addEventListener('scroll', updateNav, { passive: true });
  }

  /* ---- Mobile hamburger ---- */
  const hamburger = document.querySelector('.navbar__hamburger');
  const navWrap   = document.querySelector('.navbar__nav-wrap');
  if (hamburger && navWrap) {
    hamburger.addEventListener('click', function () {
      navWrap.classList.toggle('open');
      const expanded = navWrap.classList.contains('open');
      hamburger.setAttribute('aria-expanded', expanded);
    });

    // Close on link click
    navWrap.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        navWrap.classList.remove('open');
      });
    });
  }

  /* ---- FAQ accordion ---- */
  document.querySelectorAll('.faq-item').forEach(function (item) {
    const btn    = item.querySelector('.faq-question');
    const answer = item.querySelector('.faq-answer');
    if (!btn || !answer) return;

    btn.addEventListener('click', function () {
      const isOpen = item.classList.contains('open');

      // Close all
      document.querySelectorAll('.faq-item.open').forEach(function (openItem) {
        openItem.classList.remove('open');
        openItem.querySelector('.faq-answer').style.maxHeight = '0';
      });

      if (!isOpen) {
        item.classList.add('open');
        answer.style.maxHeight = answer.scrollHeight + 'px';
      }
    });
  });

  /* ---- Booking / contact form ---- */
  const bookingForm = document.getElementById('booking-form');
  if (bookingForm) {
    bookingForm.addEventListener('submit', function (e) {
      e.preventDefault();

      const data   = new FormData(bookingForm);
      const action = bookingForm.getAttribute('action');

      fetch(action, {
        method: 'POST',
        body: data,
        headers: { 'Accept': 'application/json' }
      })
        .then(function (res) {
          if (res.ok) {
            bookingForm.style.display = 'none';
            const success = document.getElementById('form-success');
            if (success) success.style.display = 'block';
          } else {
            res.json().then(function (json) {
              alert(json.error || 'Something went wrong. Please try again or call us directly.');
            });
          }
        })
        .catch(function () {
          alert('Network error. Please try again or contact us by phone.');
        });
    });
  }

  /* ---- Email capture form ---- */
  const emailForms = document.querySelectorAll('.email-capture__form');
  emailForms.forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      const email = form.querySelector('input[type="email"]');
      if (email && email.value) {
        form.innerHTML = '<p style="color:var(--color-primary);font-weight:700;">Thanks! You\'re subscribed. 🌿</p>';
      }
    });
  });

  /* ---- Scroll-reveal: fade-in on scroll ---- */
  if ('IntersectionObserver' in window) {
    const revealEls = document.querySelectorAll(
      '.service-card, .testimonial-card, .blog-card, .step, .who-card, .pricing-card'
    );
    const io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.style.opacity  = '1';
          entry.target.style.transform = 'translateY(0)';
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

    revealEls.forEach(function (el) {
      el.style.opacity   = '0';
      el.style.transform = 'translateY(20px)';
      el.style.transition = 'opacity 0.55s ease, transform 0.55s ease';
      io.observe(el);
    });
  }

  /* ---- Active nav link highlighting ---- */
  const currentPath = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.navbar__nav a').forEach(function (link) {
    const href = link.getAttribute('href').split('/').pop();
    if (href === currentPath || (currentPath === '' && href === 'index.html')) {
      link.style.color = 'var(--color-accent)';
    }
  });

})();
