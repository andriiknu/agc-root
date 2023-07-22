import ROOT

def define_cpp ():
    '''
    Naive implementation for generating permutations.
    Iteration is over all possible permutations repetinions are  removed on spot.
    TODO: iteration over only unique permutations
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

    # prepare lepton fields (p4, eta, phi)
    features = (

        df.Define('Electron_phi_cut', 'Electron_phi[Electron_mask]')
          .Define('Electron_eta_cut', 'Electron_eta[Electron_mask]')
          .Define(
            'Electron_p4', 
            '''
            ConstructP4 (
                    Electron_pt[Electron_mask], 
                    Electron_eta_cut, 
                    Electron_phi_cut, 
                    Electron_mass[Electron_mask]
            )
            '''
          )

          .Define('Muon_phi_cut', 'Muon_phi[Muon_mask]')
          .Define('Muon_eta_cut', 'Muon_eta[Muon_mask]')
          .Define(
            'Muon_p4', 
            '''
            ConstructP4 (
                    Muon_pt[Muon_mask], 
                    Muon_eta_cut, 
                    Muon_phi_cut, 
                    Muon_mass[Muon_mask]
            )            
            ''' 
          )

          .Define('Lepton_phi', 'Concatenate(Electron_phi_cut, Muon_phi_cut)')
          .Define('Lepton_eta', 'Concatenate(Electron_eta_cut, Muon_eta_cut)')
          .Define('Lepton_p4', 'Concatenate(Electron_p4, Muon_p4)')

    )

    # get indexes of four jets
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

    # Apply indexes to jets. Jets pt and btagCSVV2 and qgl are features itself (12 features)
    features = (
        features

             # not features themself, but needed to construct features
            .Define('JetW1_phi', 'Take(Jet_phi_cut, W1_idx)')
            .Define('JetW2_phi','Take(Jet_phi_cut, W2_idx)')
            .Define('JetbL_phi', 'Take(Jet_phi_cut, bL_idx)')
            .Define('JetbH_phi','Take(Jet_phi_cut, bH_idx)')
            .Define('JetW1_eta', 'Take(Jet_eta_cut, W1_idx)')
            .Define('JetW2_eta','Take(Jet_eta_cut, W2_idx)')
            .Define('JetbL_eta', 'Take(Jet_eta_cut, bL_idx)')
            .Define('JetbH_eta', 'Take(Jet_eta_cut, bH_idx)')

            # 12 features
            .Define('JetW1_pt', 'Take(Jet_pt_cut, W1_idx)')
            .Define('JetW2_pt','Take(Jet_pt_cut, W2_idx)')
            .Define('JetbL_pt', 'Take(Jet_pt_cut, bL_idx)')
            .Define('JetbH_pt','Take(Jet_pt_cut, bH_idx)')

            .Define('JetW1_btagCSVV2', 'Take(Jet_btagCSVV2_cut, W1_idx)')
            .Define('JetW2_btagCSVV2','Take(Jet_btagCSVV2_cut, W2_idx)')
            .Define('JetbL_btagCSVV2', 'Take(Jet_btagCSVV2_cut, bL_idx)')
            .Define('JetbH_btagCSVV2', 'Take(Jet_btagCSVV2_cut, bH_idx)')

            .Define('Jet_qgl_cut', 'Jet_qgl[Jet_mask]')
            .Define('JetW1_qgl', 'Take(Jet_qgl_cut, W1_idx)')
            .Define('JetW2_qgl','Take(Jet_qgl_cut, W2_idx)')
            .Define('JetbL_qgl', 'Take(Jet_qgl_cut, bL_idx)')
            .Define('JetbH_qgl', 'Take(Jet_qgl_cut, bH_idx)')

            # four - momentumes

            .Define(
                'JetW1_p4', 
                'ConstructP4(JetW1_pt, JetW1_eta, JetW1_phi, Take(Jet_mass_cut, W1_idx))'
            )
            .Define(
                'JetW2_p4', 
                'ConstructP4(JetW2_pt, JetW2_eta, JetW2_phi, Take(Jet_mass_cut, W2_idx))' 
            )
            .Define(
                'JetbL_p4', 
                'ConstructP4(JetbL_pt, JetbL_eta, JetbL_phi, Take(Jet_mass_cut, bL_idx))' 
            )
            .Define(
                'JetbH_p4',
                'ConstructP4(JetbH_pt, JetbH_eta, JetbH_phi, Take(Jet_mass_cut, bH_idx))' 
            )            
    )

    # build features 8 other features
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
            'M_lep', 'return Map(Lepton_p4+JetbL_p4, [] (const ROOT::Math::PxPyPzMVector &p) {return p.M();})'
        ).Define(
            'M_W', 'return Map(JetW1_p4+JetW2_p4, [] (const ROOT::Math::PxPyPzMVector &p) {return p.M();})'
        ).Define(
            'M_W_had', 'return Map(JetW1_p4+JetW2_p4+JetbH_p4, [] (const ROOT::Math::PxPyPzMVector &p) {return p.M();})'
        ).Define(
            'M_W_lep', 'return Map(JetW1_p4+JetW2_p4+JetbL_p4, [] (const ROOT::Math::PxPyPzMVector &p) {return p.M();})'
        )
    ) 


    return features
    

