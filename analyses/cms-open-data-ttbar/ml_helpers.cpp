#include "fastforest.h"
#include <cmath>
#include <assert.h>
#include <map>
#include <algorithm>
#include "ROOT/RVec.hxx"

std::map<std::string, std::vector<int>> get_permutations (std::string jet_labels) {

    std::sort(jet_labels.begin(), jet_labels.end());
    std::map<std::string, std::vector<int>> permutations;
    int count = 0, N = jet_labels.size();
    do { 
        for (int idx = 0; idx < N; ++idx) {
            std::string label = std::string(1, jet_labels[idx]);
            if (label == "o") continue;
            if (label == "w") label+=std::to_string(++count);
            permutations[label].push_back(idx);
        }
        count = 0;
    } while (std::next_permutation(jet_labels.begin(), jet_labels.end()));
    return permutations;
}

std::map<int, std::vector<ROOT::RVecI>> get_permutations_dict (size_t MAX_N_JETS) {
    std::map<int, std::vector<ROOT::RVecI> > permutations_dict;
    std::string base = "wwhl";
    for (int N = 4; N <= MAX_N_JETS; ++N) {
        std::string jet_labels = base + std::string(N-4, 'o');
        std::map<std::string, std::vector<int>> permutations = get_permutations (jet_labels);
        permutations_dict[N] = std::vector<ROOT::RVecI>{permutations["w1"], permutations["w2"], permutations["h"], permutations["l"]};
    }
    std::map<int, std::vector<ROOT::RVecI>> permutations;// = get_permutations_dict(MAX_N_JETS);
    permutations[4] = std::vector<ROOT::RVecI>{{1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3},
       {0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 2, 2},
       {2, 3, 1, 3, 0, 3, 1, 2, 0, 2, 0, 1},
       {3, 2, 3, 1, 3, 0, 2, 1, 2, 0, 1, 0}};
    return permutations;
}

std::map<std::string, fastforest::FastForest> get_fastforests (const std::string& path_to_models, size_t nfeatures) {

    std::vector<std::string> feature_names(nfeatures);
    for (int i = 0; i < nfeatures; ++i) {
        feature_names[i] = "f"+std::to_string(i);
    }

    auto fodd = fastforest::load_txt(path_to_models+"odd.txt", feature_names);
    auto feven = fastforest::load_txt(path_to_models+"even.txt", feature_names);
    return {{"even",feven}, {"odd", fodd}};
}




    
ROOT::RVecF inference(const std::vector<ROOT::RVecF> &features, const fastforest::FastForest &forest, bool check_features=false) {

    size_t npermutations = features.at(0).size();
    size_t nfeatures = features.size();
    ROOT::RVecF res(npermutations);
    float input[nfeatures];

    if (check_features) {
        for (int i = 0; i < nfeatures; ++i) {
            assert(features.at(i).size() == npermutations);
        }
    }
    
    for (int i = 0; i < npermutations; ++i) {
        for (int j = 0; j < nfeatures; ++j) {
            input[j] = features.at(j).at(i);
        }
        float score = forest(input, 0.0F);
        res[i] = 1./(1.+std::exp(-score));
    }

    return res;
}

// auto models = get_fastforests("models/", 20);
// auto feven = models["even"];
// auto fodd = models["odd"];
