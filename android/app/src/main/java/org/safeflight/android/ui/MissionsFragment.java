package org.safeflight.android.ui;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.ColorRes;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import org.safeflight.android.R;
import org.safeflight.android.databinding.FragmentMissionsBinding;
import org.safeflight.android.databinding.ItemMissionBinding;
import org.safeflight.android.mission.ExecutionMode;
import org.safeflight.android.mission.Mission;
import org.safeflight.android.mission.MissionSourceKind;
import org.safeflight.android.mission.MissionStatus;

import java.util.List;

/**
 * Missions screen (layout: res/layout/fragment_missions.xml, one card per
 * mission from res/layout/item_mission.xml). Read-only DEMO data, grouped by
 * status; nothing here can start or upload a mission.
 */
public final class MissionsFragment extends Fragment {
    private FragmentMissionsBinding binding;

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container,
                             @Nullable Bundle savedInstanceState) {
        binding = FragmentMissionsBinding.inflate(inflater, container, false);
        return binding.getRoot();
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        MainViewModel viewModel = new ViewModelProvider(requireActivity()).get(MainViewModel.class);
        binding.demoBanner.setVisibility(
                viewModel.getMissionSource() == MissionSourceKind.DEMO ? View.VISIBLE : View.GONE);
        render(viewModel.getMissions());
    }

    @Override
    public void onDestroyView() {
        binding = null;
        super.onDestroyView();
    }

    private void render(List<Mission> missions) {
        LayoutInflater inflater = getLayoutInflater();
        for (MissionStatus status : MissionStatus.values()) {
            boolean titleAdded = false;
            for (Mission mission : missions) {
                if (mission.status != status) {
                    continue;
                }
                if (!titleAdded) {
                    TextView title = (TextView) inflater.inflate(R.layout.view_section_title,
                            binding.missionsContainer, false);
                    title.setText(status.name());
                    binding.missionsContainer.addView(title);
                    titleAdded = true;
                }
                binding.missionsContainer.addView(card(inflater, mission));
            }
        }
    }

    private View card(LayoutInflater inflater, Mission m) {
        ItemMissionBinding item = ItemMissionBinding.inflate(inflater, binding.missionsContainer, false);
        item.missionTitle.setText(m.id + " · " + m.title);
        item.missionStatus.setText(m.status.name());
        item.missionStatus.setTextColor(color(statusColor(m.status)));
        boolean physical = m.executionMode == ExecutionMode.PHYSICAL;
        item.missionVehicle.setText(m.vehicle + " · " + (physical ? "FÍSICA" : "SIMULACIÓN"));
        item.missionVehicle.setTextColor(color(physical ? R.color.sf_danger : R.color.sf_muted));
        item.missionSummary.setText(m.summary);
        if (m.result != null) {
            item.missionResult.setText("Resultado: " + m.result);
            item.missionResult.setVisibility(View.VISIBLE);
        }
        if (m.error != null) {
            item.missionError.setText("Fallo: " + m.error);
            item.missionError.setVisibility(View.VISIBLE);
        }
        return item.getRoot();
    }

    @ColorRes
    private static int statusColor(MissionStatus status) {
        switch (status) {
            case APPROVED:
                return R.color.sf_accent;
            case RUNNING:
                return R.color.sf_warn;
            case COMPLETED:
                return R.color.sf_ok;
            case FAILED:
            case CANCELLED:
                return R.color.sf_danger;
            default:
                return R.color.sf_muted;
        }
    }

    private int color(@ColorRes int res) {
        return ContextCompat.getColor(requireContext(), res);
    }
}
