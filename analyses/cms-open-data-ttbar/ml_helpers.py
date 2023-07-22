import ROOT

def define_cpp ():
    '''
    Naive implementation for generating permutations.
    Iteration is over all possible permutations repetinions are  removed on spot.
    TODO: iteration over unique permutations
    '''
    ROOT.gInterpreter.Declare(
    '''
    ROOT::RVec<ROOT::RVecI> GetJetsPermutations (const ROOT::RVecD &Jets, int MAX_N_JETS)
    {
        int N;
        if ( Jets.size() >= MAX_N_JETS ) N  = MAX_N_JETS;
        else N = Jets.size();
        
        auto Labels = ROOT::RVecC ({'W', 'W', 'L', 'H'}); 
        for (int i = 4; i<N; ++i) Labels.push_back('O');

        auto indexes = ROOT::RVecI(N);
        iota(indexes.begin(), indexes.end(), 0);
        
        map<vector<char>, int> dublicates_calc;
        ROOT::RVec<ROOT::RVecI> permutations;
        
        do {

            auto labels_permutation = vector<char> (N);
            for (int i = 0; i < N; ++i) labels_permutation[i] = Labels[indexes[i]];

            if (dublicates_calc[labels_permutation]++ > 0) continue;
            
            permutations.push_back(indexes);

        } while (next_permutation(indexes.begin(), indexes.end()));

        return permutations;     
    }
    '''
)


def get_features (df: ROOT.RDataFrame, MAX_N_JETS = 6)->ROOT.RDataFrame:

    features = (
        df.Define('Electron_phi_cut', 'Electron_phi[Electron_mask]')
          .Define('Electron_eta_cut', 'Electron_eta[Electron_mask]')
          .Define('Electron_mass_cut', 'Electron_mass[Electron_mask]')
          .Define('Muon_phi_cut', 'Muon_phi[Muon_mask]')
          .Define('Muon_eta_cut', 'Muon_eta[Muon_mask]')
          .Define('Muon_mass_cut', 'Muon_mass[Muon_mask]')
          .Define('Lepton_phi', 'Concatenate(Electron_phi_cut, Muon_phi_cut)')
          .Define('Lepton_eta', 'Concatenate(Electron_eta_cut, Muon_eta_cut)')
          .Define('Lepton_mass', 'Concatenate(Electron_mass_cut, Muon_mass_cut)')
    )

    # get indexes
    features = (
        features.Define(
            'Fourjets_idx', 
            f'GetJetsPermutations(Jet_pt_cut, {MAX_N_JETS})'
        )
        .Define(
            'W1_idx', 
            'return Map(Fourjets_idx, [] (const ROOT::RVecI &e) {return e[0];});'
        )
        .Define(
            'W2_idx', 
            'return Map(Fourjets_idx, [] (const ROOT::RVecI &e) {return e[1];});'
        )
        .Define(
            'bL_idx',
            'return Map(Fourjets_idx, [] (const ROOT::RVecI &e) {return e[2];});'
        )
        .Define(
            'bH_idx',
            'return Map(Fourjets_idx, [] (const ROOT::RVecI &e) {return e[3];});'
        )
    )

    # apply indexes to get jets
    features = (
        features
            .Define('JetW1_pt', 'Take(Jet_pt_cut, W1_idx)')
            .Define('JetW2_pt','Take(Jet_pt_cut, W2_idx)')
            .Define('JetbL_pt', 'Take(Jet_pt_cut, bL_idx)')
            .Define('JetbH_pt','Take(Jet_pt_cut, bH_idx)')
            .Define('JetW1_mass', 'Take(Jet_mass_cut, W1_idx)')
            .Define('JetW2_mass','Take(Jet_mass_cut, W2_idx)')
            .Define('JetbL_mass', 'Take(Jet_mass_cut, bL_idx)')
            .Define('JetbH_mass','Take(Jet_mass_cut, bH_idx)')
            .Define('JetW1_phi', 'Take(Jet_phi_cut, W1_idx)')
            .Define('JetW2_phi','Take(Jet_phi_cut, W2_idx)')
            .Define('JetbL_phi', 'Take(Jet_phi_cut, bL_idx)')
            .Define('JetbH_phi','Take(Jet_phi_cut, bH_idx)')
            .Define('JetW1_eta', 'Take(Jet_eta_cut, W1_idx)')
            .Define('JetW2_eta','Take(Jet_eta_cut, W2_idx)')
            .Define('JetbL_eta', 'Take(Jet_eta_cut, bL_idx)')
            .Define('JetbH_eta','Take(Jet_eta_cut, bH_idx)')
    )

    features = (
        features.Define(
            'dR_lep',
            'sqrt(pow(Lepton_eta-JetbL_eta,2)+pow(Lepton_phi-JetbL_phi,2))'
        ).Define(
            'dR_W',
             'sqrt(pow(JetW1_eta-JetW2_eta,2)+pow(JetW1_phi-JetW2_phi,2))'
        ).Define(
            'dR_had1',
             'sqrt(pow(JetW1_eta-JetbH_eta,2)+pow(JetW1_phi-JetbH_phi,2))'
        ).Define(
            'dR_had2',
             'sqrt(pow(JetW2_eta-JetbH_eta,2)+pow(JetW2_phi-JetbH_phi,2))'
        ).Define(
            
        )
    ) 


    return features
    

