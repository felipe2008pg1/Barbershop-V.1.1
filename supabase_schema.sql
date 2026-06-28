-- ============================================================
-- BarberShop - Migration v2: appointment confirmation code
--
-- This migration adds support for customers to view and
-- cancel their own appointments without logging in, using
-- their phone number and a confirmation code (automatically
-- generated when the appointment is created).
--
-- This has already been executed directly in the Supabase SQL Editor.
-- This file is saved in the project as a historical record
-- of this database change.
-- ============================================================

alter table appointments
  add column if not exists confirmation_code text;

-- Ensures the code is unique per appointment
create unique index if not exists idx_appointments_confirmation_code
  on appointments (confirmation_code);
