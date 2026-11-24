package org.safeflight.android.ui.widget;

import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.util.AttributeSet;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.LinearLayout;

import androidx.annotation.ColorRes;
import androidx.core.content.ContextCompat;

import org.safeflight.android.R;
import org.safeflight.android.databinding.ViewStatusChipBinding;

/**
 * Small status indicator: "● LABEL detail" with a coloured border.
 * Layout: res/layout/view_status_chip.xml. Usage: {@code chip.bind("CONECTADO", R.color.sf_ok, null)}.
 */
public final class StatusChipView extends LinearLayout {
    private final ViewStatusChipBinding binding;
    private final GradientDrawable background = new GradientDrawable();
    private String shownKey;

    public StatusChipView(Context context) {
        this(context, null);
    }

    public StatusChipView(Context context, AttributeSet attrs) {
        super(context, attrs);
        setOrientation(HORIZONTAL);
        binding = ViewStatusChipBinding.inflate(LayoutInflater.from(context), this);
        float density = getResources().getDisplayMetrics().density;
        background.setCornerRadius(6 * density);
        background.setColor(ContextCompat.getColor(context, R.color.sf_chip_background));
        setBackground(background);
        int h = (int) (8 * density);
        int v = (int) (4 * density);
        setPadding(h, v, h, v);
        bind("", R.color.sf_muted, null);
    }

    /** Shows {@code label} in {@code color}; {@code detail} (grey) is hidden when {@code null}. */
    public void bind(String label, @ColorRes int color, String detail) {
        String key = label + "|" + color + "|" + detail;
        if (key.equals(shownKey)) {
            return; // unchanged: no redraw
        }
        shownKey = key;
        int c = ContextCompat.getColor(getContext(), color);
        background.setStroke((int) getResources().getDisplayMetrics().density, c);
        binding.chipDot.setTextColor(c);
        binding.chipLabel.setTextColor(c);
        binding.chipLabel.setText(label);
        binding.chipDetail.setVisibility(detail == null ? View.GONE : View.VISIBLE);
        binding.chipDetail.setText(detail == null ? "" : detail);
    }
}
