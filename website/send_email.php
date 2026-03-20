<?php
/**
 * Ollie Tripp Massage Therapy — Email Handler
 * Handles booking form & email subscription submissions.
 *
 * SETUP:
 * 1. Upload this file along with the rest of the website to any PHP-capable host.
 * 2. No additional configuration needed — the recipient is hardcoded below.
 * 3. Ensure your hosting provider allows mail() (most shared hosts do).
 *    Alternatively, configure PHPMailer + SMTP for higher deliverability.
 */

// ---- Configuration ----
define('RECIPIENT_EMAIL', 'ollietripmassage@gmail.com');
define('RECIPIENT_NAME',  'Ollie Tripp');
define('SITE_NAME',       'Ollie Tripp Massage Therapy');

// ---- Security headers ----
header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

// Only accept POST
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed']);
    exit;
}

// ---- Honeypot check (spam prevention) ----
if (!empty($_POST['_honeypot'])) {
    // Silently accept but don't send — it's a bot
    http_response_code(200);
    echo json_encode(['ok' => true]);
    exit;
}

// ---- Helper: sanitize input ----
function clean(string $input): string {
    return htmlspecialchars(strip_tags(trim($input)), ENT_QUOTES, 'UTF-8');
}

// ---- Determine form type ----
// Booking form has 'first_name'; subscribe form has only 'email'
$is_booking = !empty($_POST['first_name']);

if ($is_booking) {
    handle_booking();
} else {
    handle_subscribe();
}

/* =====================================================================
   BOOKING FORM HANDLER
   ===================================================================== */
function handle_booking(): void {
    // Required fields
    $required = ['first_name', 'last_name', 'email', 'phone', 'service', 'duration', 'preferred_date', 'preferred_time'];
    foreach ($required as $field) {
        if (empty($_POST[$field])) {
            http_response_code(422);
            echo json_encode(['error' => "Missing required field: {$field}"]);
            exit;
        }
    }

    // Validate email
    $email = filter_var(trim($_POST['email']), FILTER_VALIDATE_EMAIL);
    if (!$email) {
        http_response_code(422);
        echo json_encode(['error' => 'Invalid email address']);
        exit;
    }

    // Collect & sanitize
    $first       = clean($_POST['first_name']);
    $last        = clean($_POST['last_name']);
    $phone       = clean($_POST['phone']);
    $service     = clean($_POST['service']);
    $duration    = clean($_POST['duration']);
    $pref_date   = clean($_POST['preferred_date']);
    $pref_time   = clean($_POST['preferred_time']);
    $alt_date    = clean($_POST['alt_date']    ?? '');
    $new_client  = clean($_POST['new_client']  ?? 'yes');
    $concerns    = clean($_POST['concerns']    ?? '');

    // Format service label
    $service_labels = [
        'deep-tissue'    => 'Deep Tissue Massage',
        'neuromuscular'  => 'Neuromuscular Therapy',
        'sports-recovery'=> 'Sports Recovery Massage',
        'not-sure'       => 'Not Sure — Let Ollie Recommend',
    ];
    $service_label = $service_labels[$service] ?? $service;

    $duration_labels = [
        '60'  => '60 Minutes ($95)',
        '90'  => '90 Minutes ($135)',
        '120' => '120 Minutes ($175)',
    ];
    $duration_label = $duration_labels[$duration] ?? "{$duration} minutes";

    // ---- Email to Ollie ----
    $to      = RECIPIENT_NAME . ' <' . RECIPIENT_EMAIL . '>';
    $subject = "New Appointment Request — {$first} {$last}";

    $body  = "You have a new appointment request from your website.\n\n";
    $body .= "============================================================\n";
    $body .= "  CLIENT DETAILS\n";
    $body .= "============================================================\n";
    $body .= "Name:          {$first} {$last}\n";
    $body .= "Email:         {$email}\n";
    $body .= "Phone:         {$phone}\n";
    $body .= "New Client:    {$new_client}\n\n";
    $body .= "============================================================\n";
    $body .= "  APPOINTMENT DETAILS\n";
    $body .= "============================================================\n";
    $body .= "Service:       {$service_label}\n";
    $body .= "Duration:      {$duration_label}\n";
    $body .= "Preferred Date:{$pref_date}\n";
    $body .= "Preferred Time:{$pref_time}\n";
    if ($alt_date) {
        $body .= "Alt Date:      {$alt_date}\n";
    }
    if ($concerns) {
        $body .= "\n============================================================\n";
        $body .= "  AREAS OF CONCERN / NOTES\n";
        $body .= "============================================================\n";
        $body .= $concerns . "\n";
    }
    $body .= "\n------------------------------------------------------------\n";
    $body .= "Reply to this email or call {$phone} to confirm the appointment.\n";
    $body .= "Sent via " . SITE_NAME . " website contact form.\n";

    $headers  = "From: " . SITE_NAME . " <noreply@ollietrippmassage.com>\r\n";
    $headers .= "Reply-To: {$first} {$last} <{$email}>\r\n";
    $headers .= "X-Mailer: PHP/" . PHP_VERSION . "\r\n";
    $headers .= "MIME-Version: 1.0\r\n";
    $headers .= "Content-Type: text/plain; charset=UTF-8\r\n";

    $sent = mail(RECIPIENT_EMAIL, $subject, $body, $headers);

    if ($sent) {
        // ---- Confirmation email to client ----
        $confirm_subject = "We received your appointment request — " . SITE_NAME;
        $confirm_body  = "Hi {$first},\n\n";
        $confirm_body .= "Thanks for reaching out! We've received your appointment request for:\n\n";
        $confirm_body .= "  Service:  {$service_label}\n";
        $confirm_body .= "  Duration: {$duration_label}\n";
        $confirm_body .= "  Date:     {$pref_date}\n";
        $confirm_body .= "  Time:     {$pref_time}\n\n";
        $confirm_body .= "Ollie will review your request and get back to you within a few hours to confirm your appointment.\n\n";
        $confirm_body .= "If you need to reach him sooner:\n";
        $confirm_body .= "  Phone: (360) 555-0100\n";
        $confirm_body .= "  Email: " . RECIPIENT_EMAIL . "\n\n";
        $confirm_body .= "Looking forward to seeing you!\n\n";
        $confirm_body .= "— " . SITE_NAME . "\n";
        $confirm_body .= "Bellingham, WA\n";

        $confirm_headers  = "From: " . SITE_NAME . " <noreply@ollietrippmassage.com>\r\n";
        $confirm_headers .= "Reply-To: " . RECIPIENT_NAME . " <" . RECIPIENT_EMAIL . ">\r\n";
        $confirm_headers .= "MIME-Version: 1.0\r\n";
        $confirm_headers .= "Content-Type: text/plain; charset=UTF-8\r\n";

        mail($email, $confirm_subject, $confirm_body, $confirm_headers);

        http_response_code(200);
        echo json_encode(['ok' => true, 'message' => 'Appointment request sent successfully.']);
    } else {
        http_response_code(500);
        echo json_encode(['error' => 'Mail delivery failed. Please call (360) 555-0100 or email ' . RECIPIENT_EMAIL . ' directly.']);
    }
}

/* =====================================================================
   EMAIL SUBSCRIPTION HANDLER
   ===================================================================== */
function handle_subscribe(): void {
    $email = filter_var(trim($_POST['email'] ?? ''), FILTER_VALIDATE_EMAIL);
    if (!$email) {
        http_response_code(422);
        echo json_encode(['error' => 'Invalid email address']);
        exit;
    }

    $to      = RECIPIENT_EMAIL;
    $subject = 'New Email Subscriber — ' . SITE_NAME;
    $body    = "New newsletter subscriber:\n\nEmail: {$email}\n\nSent via " . SITE_NAME . " website.\n";
    $headers = "From: " . SITE_NAME . " <noreply@ollietrippmassage.com>\r\n";

    mail($to, $subject, $body, $headers);

    http_response_code(200);
    echo json_encode(['ok' => true]);
}
