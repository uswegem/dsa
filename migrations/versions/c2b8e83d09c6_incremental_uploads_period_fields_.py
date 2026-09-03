"""incremental uploads: period fields, upsert natural keys, rename upload counters

Revision ID: c2b8e83d09c6
Revises: 7849917df8fc
Create Date: 2026-09-03 18:11:49.590910

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2b8e83d09c6'
down_revision: Union[str, None] = '7849917df8fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- branch_sales -------------------------------------------------
    # Add nullable first so existing rows aren't rejected, backfill from
    # loan_date (the best available proxy for "what period is this row
    # for" on rows uploaded before period selection existed), THEN enforce
    # NOT NULL.
    op.add_column('branch_sales', sa.Column('period_month', sa.Integer(), nullable=True))
    op.add_column('branch_sales', sa.Column('period_year', sa.Integer(), nullable=True))
    op.add_column('branch_sales', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))

    op.execute("""
        UPDATE branch_sales
        SET period_month = EXTRACT(MONTH FROM loan_date)::int,
            period_year = EXTRACT(YEAR FROM loan_date)::int
        WHERE loan_date IS NOT NULL AND period_month IS NULL
    """)
    # Any row with no loan_date at all (shouldn't occur under current
    # ingestion rules, but defends pre-existing/demo data) falls back to today.
    op.execute("""
        UPDATE branch_sales
        SET period_month = EXTRACT(MONTH FROM CURRENT_DATE)::int,
            period_year = EXTRACT(YEAR FROM CURRENT_DATE)::int
        WHERE period_month IS NULL
    """)

    op.alter_column('branch_sales', 'period_month', nullable=False)
    op.alter_column('branch_sales', 'period_year', nullable=False)
    op.create_unique_constraint('uq_branch_sales_natural_key', 'branch_sales', ['client_account_no', 'period_month', 'period_year'])
    op.drop_column('branch_sales', 'date_out_of_period_warning')

    # --- business_transactions -----------------------------------------
    op.add_column('business_transactions', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.create_unique_constraint('uq_business_transactions_natural_key', 'business_transactions', ['client_disb_ext_account_no', 'loan_type', 'disbursement_date'])

    # --- uploads ---------------------------------------------------------
    # period_month/period_year stay nullable: legacy uploads (before this
    # field existed) have no reliable single period to backfill from
    # (an upload can touch many branch_sales rows with different loan_dates).
    op.add_column('uploads', sa.Column('period_month', sa.Integer(), nullable=True))
    op.add_column('uploads', sa.Column('period_year', sa.Integer(), nullable=True))
    op.alter_column('uploads', 'valid_rows', new_column_name='rows_accepted')
    op.alter_column('uploads', 'error_rows', new_column_name='rows_rejected')


def downgrade() -> None:
    op.alter_column('uploads', 'rows_accepted', new_column_name='valid_rows')
    op.alter_column('uploads', 'rows_rejected', new_column_name='error_rows')
    op.drop_column('uploads', 'period_year')
    op.drop_column('uploads', 'period_month')

    op.drop_constraint('uq_business_transactions_natural_key', 'business_transactions', type_='unique')
    op.drop_column('business_transactions', 'updated_at')

    op.add_column('branch_sales', sa.Column('date_out_of_period_warning', sa.BOOLEAN(), server_default=sa.text('false'), nullable=False))
    op.drop_constraint('uq_branch_sales_natural_key', 'branch_sales', type_='unique')
    op.drop_column('branch_sales', 'updated_at')
    op.drop_column('branch_sales', 'period_year')
    op.drop_column('branch_sales', 'period_month')
