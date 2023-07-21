import ROOT

def define_cpp ():
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
        df.Define('Fourjets_idx', f'GetJetsPermutations(Jet_pt_cut, {MAX_N_JETS})')
        .Define(
            'w1_idx', 
            'return Map(Fourjets_idx, [] (const ROOT::RVecI &e) {return e[0];});'
        )
        .Define(
            'w2_idx', 
            'return Map(Fourjets_idx, [] (const ROOT::RVecI &e) {return e[1];});'
        )
        .Define(
            'b_toplep_idx',
            'return Map(Fourjets_idx, [] (const ROOT::RVecI &e) {return e[2];});'
        )
        .Define(
            'b_tophad_idx',
            'return Map(Fourjets_idx, [] (const ROOT::RVecI &e) {return e[3];});'
        )
    )
    return features
    

